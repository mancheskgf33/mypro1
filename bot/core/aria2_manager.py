from aioaria2 import Aria2WebsocketClient
from asyncio import gather
from pathlib import Path

from .. import LOGGER, aria2_options



class Aria2Manager:
    aria2 = None

    @classmethod
    async def initiate(cls):
        cls.aria2 = await Aria2WebsocketClient.new("http://localhost:6800/jsonrpc")

    @classmethod
    async def close_all(cls):
        if cls.aria2:
            await cls.aria2.close()

    @classmethod
    async def aria2_remove(cls, download):
        if not cls.aria2:
            return
        gid = download.get("gid", "")
        if download.get("status", "") in ["active", "paused", "waiting"]:
            await cls.aria2.forceRemove(gid)
        else:
            try:
                await cls.aria2.removeDownloadResult(gid)
            except Exception:
                pass

    @classmethod
    async def remove_all(cls):
        if not cls.aria2:
            return
        await cls.aria2.forcePauseAll()
        await cls.aria2.purgeDownloadResult()
        results = await gather(cls.aria2.tellActive(), cls.aria2.tellWaiting(0, 1000))
        tasks = [cls.aria2.forceRemove(item.get("gid")) for group in results for item in group]
        if tasks:
            await gather(*tasks, return_exceptions=True)

    @classmethod
    async def overall_speed(cls):
        stats = await cls.aria2.getGlobalStat()
        return int(stats.get("downloadSpeed", "0")), int(stats.get("uploadSpeed", "0"))

    @classmethod
    async def pause_all(cls):
        if cls.aria2:
            await cls.aria2.forcePauseAll()

    @classmethod
    async def change_aria2_option(cls, key, value):
        downloads = []
        results = await gather(cls.aria2.tellActive(), cls.aria2.tellWaiting(0, 1000))
        for group in results:
            downloads.extend(group)
        tasks = [
            cls.aria2.changeOption(item.get("gid"), {key: value})
            for item in downloads
            if item.get("status", "") != "complete"
        ]
        if tasks:
            await gather(*tasks, return_exceptions=True)
        if key not in ["checksum", "index-out", "out", "pause", "select-file"]:
            await cls.aria2.changeGlobalOption({key: value})
            aria2_options[key] = value


def aria2_name(download_info):
    files = download_info.get("files", [])
    if not files:
        return ""
    file_path = files[0].get("path", "")
    if not file_path:
        return ""
    dir_path = download_info.get("dir", "")
    if dir_path and file_path.startswith(dir_path):
        parts = Path(file_path[len(dir_path) + 1 :]).parts
        return parts[0] if parts else Path(file_path).name
    return Path(file_path).name
