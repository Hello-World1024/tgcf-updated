"""The module responsible for operating tgcf in live mode."""

import logging
import os
import sys
from typing import Union

from telethon import TelegramClient, events, functions, types
from telethon.sessions import StringSession
from telethon.tl.custom.message import Message

from tgcf import config, const
from tgcf import storage as st
from tgcf.bot import get_events
from tgcf.config import CONFIG, get_SESSION
from tgcf.plugins import apply_plugins, load_async_plugins
from tgcf.utils import clean_session_files, send_message
from tgcf import forward_count
from tgcf.random_handler import RandomMessageHandler
import asyncio
import time
from datetime import datetime, timedelta

# Rate limiting for Render optimization
last_forward_time = {}
FORWARD_DELAY = 0.5  # 500ms delay between forwards to prevent CPU spikes
BURST_LIMIT = 10  # Max messages per minute per chat
burst_tracker = {}


async def new_message_handler(event: Union[Message, events.NewMessage]) -> None:
    """Process new incoming messages with rate limiting for Render."""
    chat_id = event.chat_id

    if chat_id not in config.from_to:
        return
    
    # Implement rate limiting for Render free tier
    current_time = time.time()
    
    # Check burst limit (max 10 messages per minute per chat)
    if chat_id not in burst_tracker:
        burst_tracker[chat_id] = []
    
    # Clean old entries (older than 1 minute)
    burst_tracker[chat_id] = [t for t in burst_tracker[chat_id] if current_time - t < 60]
    
    if len(burst_tracker[chat_id]) >= BURST_LIMIT:
        logging.warning(f"Rate limit reached for chat {chat_id}, delaying message processing")
        await asyncio.sleep(5)  # Wait 5 seconds before processing
    
    burst_tracker[chat_id].append(current_time)
    
    # Add delay between forwards to prevent CPU spikes
    if chat_id in last_forward_time:
        time_since_last = current_time - last_forward_time[chat_id]
        if time_since_last < FORWARD_DELAY:
            delay = FORWARD_DELAY - time_since_last
            await asyncio.sleep(delay)
    
    last_forward_time[chat_id] = time.time()
    
    logging.info(f"Processing message from {chat_id} (rate-limited)")

    forward_data = config.from_to.get(chat_id)
    limit = forward_data.get("limit")
    dest = forward_data.get("dests")
    watermark_text = forward_data.get("watermark_text")

    if limit and limit > 0:
        count = forward_count.get_forward_count(chat_id)
        if count >= limit:
            logging.warning(
                f"Daily forward limit reached for source {chat_id}. Limit={limit}, Count={count}"
            )
            return

    message = event.message

    event_uid = st.EventUid(event)

    length = len(st.stored)
    exceeding = length - const.KEEP_LAST_MANY

    if exceeding > 0:
        for key in st.stored:
            del st.stored[key]
            break

    tm = await apply_plugins(message)
    if not tm:
        return

    if watermark_text:
        if tm.text:
            tm.text = f"{tm.text}\n\n{watermark_text}"
        else:
            tm.text = watermark_text

    if event.is_reply:
        r_event = st.DummyEvent(chat_id, event.reply_to_msg_id)
        r_event_uid = st.EventUid(r_event)

    st.stored[event_uid] = {}
    for d in dest:
        if event.is_reply and r_event_uid in st.stored:
            tm.reply_to = st.stored.get(r_event_uid).get(d)
        fwded_msg = await send_message(d, tm)
        st.stored[event_uid].update({d: fwded_msg})

    if limit and limit > 0:
        forward_count.increment_forward_count(chat_id)

    tm.clear()


async def edited_message_handler(event) -> None:
    """Handle message edits."""
    message = event.message

    chat_id = event.chat_id

    if chat_id not in config.from_to:
        return

    logging.info(f"Message edited in {chat_id}")

    event_uid = st.EventUid(event)

    tm = await apply_plugins(message)

    if not tm:
        return

    fwded_msgs = st.stored.get(event_uid)

    if fwded_msgs:
        for _, msg in fwded_msgs.items():
            if config.CONFIG.live.delete_on_edit == message.text:
                await msg.delete()
                await message.delete()
            else:
                await msg.edit(tm.text)
        return

    dest = config.from_to.get(chat_id)

    for d in dest:
        await send_message(d, tm)
    tm.clear()


async def deleted_message_handler(event):
    """Handle message deletes."""
    chat_id = event.chat_id
    if chat_id not in config.from_to:
        return

    logging.info(f"Message deleted in {chat_id}")

    event_uid = st.EventUid(event)
    fwded_msgs = st.stored.get(event_uid)
    if fwded_msgs:
        for _, msg in fwded_msgs.items():
            await msg.delete()
        return


ALL_EVENTS = {
    "new": (new_message_handler, events.NewMessage()),
    "edited": (edited_message_handler, events.MessageEdited()),
    "deleted": (deleted_message_handler, events.MessageDeleted()),
}


async def start_sync() -> None:
    """Start tgcf live sync."""
    # clear past session files
    clean_session_files()

    # load async plugins defined in plugin_models
    await load_async_plugins()

    SESSION = get_SESSION()
    client = TelegramClient(
        SESSION,
        CONFIG.login.API_ID,
        CONFIG.login.API_HASH,
        sequential_updates=CONFIG.live.sequential_updates,
    )
    if CONFIG.login.user_type == 0:
        if CONFIG.login.BOT_TOKEN == "":
            logging.warning("Bot token not found, but login type is set to bot.")
            sys.exit()
        await client.start(bot_token=CONFIG.login.BOT_TOKEN)
    else:
        await client.start()
    config.is_bot = await client.is_bot()
    logging.info(f"config.is_bot={config.is_bot}")
    await config.load_admins(client)

    if CONFIG.use_telegram_bot:
        command_events = get_events()
        ALL_EVENTS.update(command_events)

    for key, val in ALL_EVENTS.items():
        if config.CONFIG.live.delete_sync is False and key == "deleted":
            continue
        client.add_event_handler(*val)
        logging.info(f"Added event handler for {key}")

    if config.is_bot and const.REGISTER_COMMANDS:
        await client(
            functions.bots.SetBotCommandsRequest(
                scope=types.BotCommandScopeDefault(),
                lang_code="en",
                commands=[
                    types.BotCommand(command=key, description=value)
                    for key, value in const.COMMANDS.items()
                ],
            )
        )
    config.from_to = await config.load_from_to(client, config.CONFIG.forwards)
    
    # Initialize and start random message handler
    random_handler = RandomMessageHandler(client)
    try:
        await random_handler.start()
        logging.info("Random message handler started successfully")
        
        # Run the client until disconnected
        await client.run_until_disconnected()
    finally:
        # Clean up random handler
        await random_handler.stop()
        logging.info("Random message handler stopped")
