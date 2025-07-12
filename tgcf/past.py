"""The module for running tgcf in past mode.

- past mode can only operate with a user account.
- past mode deals with all existing messages.
"""

"""Patch for past.py to fix the private channel issue"""

import asyncio
import logging
import time

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import FloodWaitError
from telethon.tl.custom.message import Message
from telethon.tl.patched import MessageService

from tgcf import config
from tgcf import storage as st
from tgcf.config import CONFIG, get_SESSION, write_config
from tgcf.plugins import apply_plugins, load_async_plugins
from tgcf.utils import clean_session_files, send_message
from tgcf.state_manager import get_state_manager


async def forward_job() -> None:
    """Forward all existing messages in the concerned chats."""
    # Initialize state manager
    state_manager = get_state_manager()
    
    # Load previous processing state if available
    app_state = state_manager.load_application_state()
    if app_state:
        logging.info(f"Resuming past mode from previous session: {app_state.get('running_since')}")
    
    clean_session_files()

    # load async plugins defined in plugin_models
    await load_async_plugins()    

    if CONFIG.login.user_type != 1:
        logging.warning(
            "You cannot use bot account for tgcf past mode. Telegram does not allow bots to access chat history."
        )
        return
    SESSION = get_SESSION()
    
    try:
        async with TelegramClient(
            SESSION, CONFIG.login.API_ID, CONFIG.login.API_HASH
        ) as client:
            config.from_to = await config.load_from_to(client, config.CONFIG.forwards)
            client: TelegramClient
            
            # Save initial application state
            import hashlib
            from datetime import datetime
            config_hash = hashlib.md5(str(CONFIG.dict()).encode()).hexdigest()
            active_forwards = list(config.from_to.keys())
            state_manager.save_application_state(
                mode="past",
                config_hash=config_hash,
                running_since=datetime.utcnow(),
                active_forwards=active_forwards
            )
            
            for from_to, forward in zip(config.from_to.items(), config.CONFIG.forwards):
                src, dest_data = from_to
                last_id = 0
                forward: config.Forward
                
                # Load previous processing state for this chat
                chat_state = state_manager.load_message_processing_state(src)
                if chat_state:
                    last_id = chat_state.get('last_message_id', 0)
                    saved_offset = chat_state.get('offset', forward.offset)
                    if saved_offset > forward.offset:
                        forward.offset = saved_offset
                        logging.info(f"Resuming from saved offset {saved_offset} for chat {src}")
            
            # Extract destinations
            dest = dest_data.get("dests", [])
            
            # Debug log
            logging.info(f"Source: {src}, Destinations: {dest}")
            
            async for message in client.iter_messages(
                src, reverse=True, offset_id=forward.offset
            ):
                message: Message
                event = st.DummyEvent(message.chat_id, message.id)
                event_uid = st.EventUid(event)

                if forward.end and last_id > forward.end:
                    continue
                if isinstance(message, MessageService):
                    continue
                try:
                    forward_data = config.from_to.get(src)
                    tm = await apply_plugins(message, forward_data)
                    if not tm:
                        continue
                    
                    st.stored[event_uid] = {}

                    if message.is_reply:
                        r_event = st.DummyEvent(
                            message.chat_id, message.reply_to_msg_id
                        )
                        r_event_uid = st.EventUid(r_event)
                    
                    for d in dest:
                        # Try to convert string to integer if it's a numeric string
                        try:
                            if isinstance(d, str) and d.strip('-').isdigit():
                                d = int(d)
                                logging.info(f"Converted string destination '{d}' to integer")
                        except Exception as e:
                            logging.warning(f"Error converting destination: {e}")
                            
                        logging.info(f"Forwarding to destination: {d} (type: {type(d).__name__})")
                        
                        if message.is_reply and r_event_uid in st.stored:
                            tm.reply_to = st.stored.get(r_event_uid).get(d)
                        
                        try:
                            fwded_msg = await send_message(d, tm)
                            st.stored[event_uid].update({d: fwded_msg.id})
                            logging.info(f"Successfully forwarded to {d}")
                        except Exception as e:
                            logging.error(f"Failed to forward to {d}: {e}")
                            
                    tm.clear()
                    last_id = message.id
                    logging.info(f"forwarding message with id = {last_id}")
                    forward.offset = last_id
                    
                    # Save state periodically
                    state_manager.save_message_processing_state(
                        chat_id=src,
                        last_message_id=last_id,
                        offset=forward.offset
                    )
                    
                    write_config(CONFIG, persist=False)
                    time.sleep(CONFIG.past.delay)
                    logging.info(f"slept for {CONFIG.past.delay} seconds")

                except FloodWaitError as fwe:
                    logging.info(f"Sleeping for {fwe}")
                    await asyncio.sleep(delay=fwe.seconds)
                except Exception as err:
                    logging.exception(err)
                    
            # Mark session as completed
            state_manager.mark_session_ended("past_mode_completed")
            logging.info("Past mode processing completed successfully")
            
    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt, shutting down gracefully...")
        state_manager.mark_session_ended("keyboard_interrupt")
    except Exception as e:
        logging.error(f"Unexpected error in past mode: {e}")
        state_manager.mark_session_ended(f"error: {str(e)}")
    finally:
        # Clean up old sessions
        state_manager.cleanup_old_sessions()
        logging.info("Past mode shutdown complete")
