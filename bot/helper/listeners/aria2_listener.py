from asyncio import TimeoutError, sleep
from aiohttp.client_exceptions import ClientError

from ... import LOGGER
from ...core.aria2_manager import Aria2Manager, aria2_name
from ..ext_utils.status_utils import get_task_by_gid
from ..ext_utils.task_manager import stop_duplicate_check


async def _on_download_started(api, data):
    gid = data["params"][0]["gid"]
    await sleep(2)
    try:
        download = await api.tellStatus(gid)
    except Exception as exc:
        LOGGER.warning(f"Unable to inspect aria2 download {gid}: {exc}")
        return
    if task := await get_task_by_gid(gid):
        task.listener.name = aria2_name(download)
        msg, button = await stop_duplicate_check(task.listener)
        if msg:
            await Aria2Manager.aria2_remove(download)
            await task.listener.on_download_error(msg, button)


async def _on_download_complete(api, data):
    gid = data["params"][0]["gid"]
    try:
        download = await api.tellStatus(gid)
    except (TimeoutError, ClientError, Exception) as exc:
        LOGGER.error(f"aria2 completion callback failed: {exc}")
        return
    LOGGER.info(f"HTTP(S) download completed: {aria2_name(download)} - Gid: {gid}")
    if task := await get_task_by_gid(gid):
        await task.listener.on_download_complete()
    await Aria2Manager.aria2_remove(download)


async def _on_download_error(api, data):
    gid = data["params"][0]["gid"]
    await sleep(1)
    try:
        download = await api.tellStatus(gid)
        error = download.get("errorMessage", "Download failed")
    except Exception as exc:
        error = str(exc)
    if task := await get_task_by_gid(gid):
        await task.listener.on_download_error(error)


def add_aria2_callbacks():
    Aria2Manager.aria2.onDownloadComplete(_on_download_complete)
    Aria2Manager.aria2.onDownloadError(_on_download_error)
    Aria2Manager.aria2.onDownloadStart(_on_download_started)
