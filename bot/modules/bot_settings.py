from asyncio import sleep
from pyrogram.filters import create
from pyrogram.handlers import MessageHandler
from time import time

from .. import LOGGER
from ..core.config_manager import Config
from ..core.telegram_manager import TgClient
from ..helper.ext_utils.bot_utils import new_task
from ..helper.ext_utils.db_handler import database
from ..helper.telegram_helper.button_build import ButtonMaker
from ..helper.telegram_helper.message_utils import (
    send_message,
    edit_message,
    delete_message,
)

PER_PAGE = 20
SECRETS = ("TOKEN", "HASH", "PASS", "API", "SESSION", "URL", "KEY")
state = {"editing": False}


def _keys(query=""):
    keys = sorted(Config.get_all().keys())
    if query:
        keys = [k for k in keys if query.lower() in k.lower()]
    return keys


def _mask(key, value):
    text = str(value)
    if value and any(s in key for s in SECRETS):
        return text[:3] + "***" if len(text) > 3 else "***"
    return text if len(text) < 300 else text[:300] + "..."


async def _main_menu(page=0, query=""):
    keys = _keys(query)
    pages = max(1, (len(keys) + PER_PAGE - 1) // PER_PAGE)
    page = min(max(page, 0), pages - 1)
    buttons = ButtonMaker()
    for key in keys[page * PER_PAGE : (page + 1) * PER_PAGE]:
        buttons.data_button(key, f"botset key {key} {page}")
    if page > 0:
        buttons.data_button("⬅️", f"botset page {page - 1}", "footer")
    buttons.data_button(f"{page + 1}/{pages}", "botset noop", "footer")
    if page < pages - 1:
        buttons.data_button("➡️", f"botset page {page + 1}", "footer")
    buttons.data_button("Close", "botset close", "footer")
    return f"<b>Bot Settings</b> ({len(keys)} keys)", buttons.build_menu(2)


async def _key_menu(key, page):
    buttons = ButtonMaker()
    buttons.data_button("Edit", f"botset edit {key} {page}")
    buttons.data_button("Back", f"botset page {page}")
    buttons.data_button("Close", "botset close", "footer")
    text = f"<b>{key}</b>\n\n<code>{_mask(key, Config.get(key))}</code>"
    return text, buttons.build_menu(2)


@new_task
async def send_bot_settings(_, message):
    query = message.command[1] if len(message.command) > 1 else ""
    text, markup = await _main_menu(0, query)
    await send_message(message, text, markup)


async def _wait_value(client, query, key, page):
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    result = {}
    state["editing"] = True

    async def _filter(_, __, event):
        user = event.from_user or event.sender_chat
        return bool(user.id == user_id and event.chat.id == chat_id and event.text)

    async def _handler(_, message):
        result["value"] = message.text
        await delete_message(message)
        state["editing"] = False

    handler = client.add_handler(MessageHandler(_handler, filters=create(_filter)), group=-1)
    start = time()
    while state["editing"] and time() - start < 60:
        await sleep(0.5)
    state["editing"] = False
    client.remove_handler(*handler)
    if "value" in result:
        try:
            Config.set(key, result["value"])
            await database.update_config({key: Config.get(key)})
        except Exception as e:
            LOGGER.error(e)
            await query.answer(f"Error: {e}", show_alert=True)
    text, markup = await _key_menu(key, page)
    await edit_message(query.message, text, markup)


@new_task
async def edit_bot_settings(client, query):
    data = query.data.split()
    if query.from_user.id != Config.OWNER_ID:
        return await query.answer("Not Yours!", show_alert=True)
    action = data[1]
    if action == "noop":
        await query.answer()
    elif action == "close":
        await query.answer()
        await delete_message(query.message)
    elif action == "page":
        await query.answer()
        text, markup = await _main_menu(int(data[2]))
        await edit_message(query.message, text, markup)
    elif action == "key":
        await query.answer()
        text, markup = await _key_menu(data[2], data[3])
        await edit_message(query.message, text, markup)
    elif action == "edit":
        await query.answer()
        buttons = ButtonMaker()
        buttons.data_button("Cancel", f"botset key {data[2]} {data[3]}")
        await edit_message(
            query.message,
            f"Send new value for <b>{data[2]}</b>. Timeout: 60s",
            buttons.build_menu(1),
        )
        await _wait_value(client, query, data[2], data[3])
