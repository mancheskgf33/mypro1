import asyncio
from os import path as ospath
from typing import Any, Awaitable, Callable
from httpx import AsyncClient, HTTPError

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException

_API_BASE = "https://api.torbox.app/v1/api"
_TIMEOUT = 45.0
_POLL_INTERVAL = 5.0
_MAX_WAIT = 7200.0
_UNLOCK_CONCURRENCY = 3

_READY_STATES = {"cached", "completed", "uploading"}
_ERROR_STATES = {
    "error",
    "failed",
    "missingfiles",
    "stalled",

    "dead",
    "unknown",
}


def _token() -> str:
    if token := (getattr(Config, "TORBOX_API_KEY", "") or "").strip():
        return token
    else:
        raise DirectDownloadLinkException("ERROR: TORBOX_API_KEY is not configured")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "User-Agent": "mltb-torbox/1.0",
    }


def _err(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(
            payload.get("detail")
            or payload.get("message")
            or payload.get("error")
            or payload
        )
    return str(payload)


async def _api(
    method: str,
    endpoint: str,
    *,
    params: dict[str, Any] | None = None,
    data: Any = None,
    files: Any = None,
) -> Any:
    try:
        async with AsyncClient(timeout=_TIMEOUT, headers=_headers()) as client:
            res = await client.request(
                method,
                f"{_API_BASE}{endpoint}",
                params=params or {},
                data=data,
                files=files,
            )
            res.raise_for_status()
            payload = res.json()
    except HTTPError as exc:
        raise DirectDownloadLinkException(
            f"ERROR: TorBox network error: {exc}"
        ) from exc
    except ValueError as exc:
        raise DirectDownloadLinkException(
            f"ERROR: TorBox returned malformed JSON: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise DirectDownloadLinkException("ERROR: TorBox returned unexpected payload")

    if payload.get("success") is not True:
        raise DirectDownloadLinkException(f"ERROR: TorBox: {_err(payload)}")

    return payload.get("data")


def _first_item(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        return data[0] if data else {}

    if isinstance(data, dict):
        return next(
            (
                data[key]
                for key in ("webdl", "download", "item")
                if isinstance(data.get(key), dict)
            ),
            data,
        )
    return {}


def _is_ready(item: dict[str, Any]) -> bool:
    if item.get("download_finished") is True or item.get("download_present") is True:
        return True

    state = str(item.get("download_state") or "").lower()
    return state in _READY_STATES and bool(item.get("files"))


def _has_error(item: dict[str, Any]) -> str:
    if item.get("error"):
        return str(item["error"])

    state = str(item.get("download_state") or "").lower()
    return state if state in _ERROR_STATES else ""


def _basename(name: str) -> str:
    return ospath.basename(name.rstrip("/")) or "file"




async def _create_webdl(link: str) -> dict[str, Any]:
    LOGGER.info("TorBox: creating web download")
    files = {"link": (None, link)}
    data = await _api("POST", "/webdl/createwebdownload", files=files)
    if item := _first_item(data):
        return item
    else:
        raise DirectDownloadLinkException("ERROR: TorBox returned no webdl data")



async def _get_webdl(web_id: int | str) -> dict[str, Any]:
    data = await _api(
        "GET",
        "/webdl/mylist",
        params={"id": str(web_id), "bypass_cache": "true"},
    )
    if item := _first_item(data):
        return item
    else:
        raise DirectDownloadLinkException(
            f"ERROR: TorBox returned no webdl status for {web_id}"
        )



async def delete_web_download(web_id: int | str) -> bool:
    try:
        await _api(
            "POST",
            "/webdl/controlwebdownload",
            data={"web_id": str(web_id), "operation": "Delete"},
        )
        return True
    except Exception as exc:
        LOGGER.warning(f"TorBox: failed to delete webdl {web_id}: {exc}")
        return False


async def _wait_ready(
    item_id: int | str,
    *,
    is_cancelled: Callable[[], bool] | None = None,
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    loop = asyncio.get_event_loop()
    started = loop.time()

    while True:
        if is_cancelled and is_cancelled():
            raise DirectDownloadLinkException("ERROR: TorBox task cancelled")

        item = await _get_webdl(item_id)

        if progress_callback:
            await progress_callback(
                {
                    "phase": "webdl",
                    "name": item.get("name"),
                    "state": item.get("download_state"),
                    "progress": item.get("progress"),
                    "eta": item.get("eta"),
                }
            )

        if _is_ready(item):
            return item

        if err := _has_error(item):
            raise DirectDownloadLinkException(f"ERROR: TorBox WebDL failed: {err}")

        now = loop.time()

        if now - started >= _MAX_WAIT:
            raise DirectDownloadLinkException("ERROR: TorBox max wait timeout")

        await asyncio.sleep(_POLL_INTERVAL)


async def _request_file_link(item_id: int | str, file_id: int | str) -> str:
    params = {
        "token": _token(),
        "web_id": str(item_id),
        "file_id": str(file_id),
    }

    last_exc = None

    for attempt in range(1, 4):
        try:
            data = await _api("GET", "/webdl/requestdl", params=params)
            if isinstance(data, str) and data:
                return data
            raise DirectDownloadLinkException("ERROR: TorBox did not return direct URL")
        except Exception as exc:
            last_exc = exc
            if attempt < 3:
                await asyncio.sleep(attempt * 2)
                continue
            raise

    raise DirectDownloadLinkException(f"ERROR: TorBox requestdl failed: {last_exc}")


async def _payload(item: dict[str, Any], item_id: int | str) -> dict[str, Any]:
    files = item.get("files") or []

    if not isinstance(files, list) or not files:
        raise DirectDownloadLinkException("ERROR: TorBox returned no files")

    semaphore = asyncio.Semaphore(_UNLOCK_CONCURRENCY)
    contents: list[dict[str, Any]] = []

    async def one(file_item: dict[str, Any]):
        file_id = file_item.get("id")
        if file_id is None:
            return

        async with semaphore:
            direct = await _request_file_link(item_id, file_id)

        full_name = file_item.get("name") or file_item.get("short_name") or "file"

        contents.append(
            {
                "filename": file_item.get("short_name") or _basename(full_name),
                "path": full_name,
                "url": direct,
                "size": int(file_item.get("size") or 0),
                "headers": {},
            }
        )

    await asyncio.gather(*(one(f) for f in files if isinstance(f, dict)))

    if not contents:
        raise DirectDownloadLinkException("ERROR: TorBox could not create direct links")

    return {
        "title": item.get("name") or "TorBox",
        "total_size": sum(x["size"] for x in contents),
        "contents": contents,
    }




async def torbox_resolve(
    link: str,
    *,
    is_cancelled: Callable[[], bool] | None = None,
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    entry = await _create_webdl(link)
    web_id = entry.get("webdownload_id") or entry.get("web_id") or entry.get("id")

    if not web_id:
        raise DirectDownloadLinkException("ERROR: TorBox did not return webdownload_id")

    try:
        item = await _wait_ready(
            web_id,
            is_cancelled=is_cancelled,
            progress_callback=progress_callback,
        )
        result = await _payload(item, web_id)
        result["torbox_web_id"] = web_id
        return result
    except Exception:
        await delete_web_download(web_id)
        raise
