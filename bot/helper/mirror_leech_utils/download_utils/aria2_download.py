from aiohttp.client_exceptions import ClientError
from asyncio import TimeoutError

from .... import task_dict_lock, task_dict, LOGGER
from ....core.aria2_manager import Aria2Manager, aria2_name
from ...ext_utils.task_manager import check_running_tasks
from ...mirror_leech_utils.status_utils.aria2_status import Aria2Status
from ...telegram_helper.message_utils import send_status_message


async def add_aria2_download(listener, dpath, header):
    options = {"dir": dpath}
    if listener.name:
        options["out"] = listener.name
    if header:
        options["header"] = header

    add_to_queue, event = await check_running_tasks(listener)
    if add_to_queue:
        options["pause"] = "true"

    try:
        gid = await Aria2Manager.aria2.addUri(uris=[listener.link], options=options)
        download = await Aria2Manager.aria2.tellStatus(gid)
    except (TimeoutError, ClientError, Exception) as exc:
        LOGGER.info(f"Aria2 HTTP(S) download error: {exc}")
        await listener.on_download_error(str(exc))
        return

    if download.get("errorMessage"):
        error = str(download["errorMessage"]).replace("<", " ").replace(">", " ")
        await Aria2Manager.aria2_remove(download)
        await listener.on_download_error(error)
        return

    async with task_dict_lock:
        task_dict[listener.mid] = Aria2Status(listener, gid, queued=add_to_queue)

    LOGGER.info(f"Aria2 HTTP(S) download started: {aria2_name(download)} - Gid: {gid}")
    await listener.on_download_start()
    if not add_to_queue and listener.multi <= 1 and not listener.is_rss:
        await send_status_message(listener.message)

    if add_to_queue:
        await event.wait()
        if listener.is_cancelled:
            return
        async with task_dict_lock:
            task = task_dict.get(listener.mid)
            if task is None:
                return
            task.queued = False
            await task.update()
            new_gid = task.gid()
        await Aria2Manager.aria2.unpause(new_gid)
