from .... import LOGGER
from ....core.aria2_manager import Aria2Manager, aria2_name
from ...ext_utils.status_utils import MirrorStatus, get_readable_time, get_readable_file_size
from time import time


async def get_download(gid, old_info=None):
    try:
        return await Aria2Manager.aria2.tellStatus(gid) or old_info
    except Exception as exc:
        LOGGER.error(f"Aria2 status lookup failed: {exc}")
        return old_info


class Aria2Status:
    def __init__(self, listener, gid, queued=False):
        self._gid = gid
        self._download = {}
        self.listener = listener
        self.queued = queued
        self.start_time = time()
        self.tool = "aria2"

    async def update(self):
        self._download = await get_download(self._gid, self._download)
        if self._download.get("followedBy"):
            self._gid = self._download["followedBy"][0]
            self._download = await get_download(self._gid)

    def progress(self):
        try:
            total = int(self._download.get("totalLength", "0"))
            done = int(self._download.get("completedLength", "0"))
            return f"{round(done / total * 100, 2)}%" if total else "0%"
        except Exception:
            return "0%"

    def processed_bytes(self):
        return get_readable_file_size(int(self._download.get("completedLength", "0")))

    def speed(self):
        return f"{get_readable_file_size(int(self._download.get('downloadSpeed', '0')))}/s"

    def name(self):
        return aria2_name(self._download)

    def size(self):
        return get_readable_file_size(int(self._download.get("totalLength", "0")))

    def eta(self):
        try:
            remaining = int(self._download.get("totalLength", "0")) - int(self._download.get("completedLength", "0"))
            speed = int(self._download.get("downloadSpeed", "0"))
            return get_readable_time(remaining / speed) if speed else "-"
        except Exception:
            return "-"

    async def status(self):
        await self.update()
        if self._download.get("status") == "waiting" or self.queued:
            return MirrorStatus.STATUS_QUEUEDL
        if self._download.get("status") == "paused":
            return MirrorStatus.STATUS_PAUSED
        return MirrorStatus.STATUS_DOWNLOAD

    def task(self):
        return self

    def gid(self):
        return self._gid

    async def cancel_task(self):
        self.listener.is_cancelled = True
        await self.update()
        await Aria2Manager.aria2_remove(self._download)
        if self.queued:
            LOGGER.info(f"Cancelling queued HTTP download: {self.name()}")
            msg = "Task removed from download queue"
        else:
            LOGGER.info(f"Cancelling HTTP download: {self.name()}")
            msg = "Stopped by user!"
        await self.listener.on_download_error(msg)
