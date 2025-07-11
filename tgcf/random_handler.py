"""Random message handler for live mode."""

import asyncio
import logging
import random
import time
from typing import Dict, List, Optional

from telethon import TelegramClient
from telethon.tl.custom.message import Message
from telethon.tl.patched import MessageService

from tgcf import config, storage as st
from tgcf.config import CONFIG
from tgcf.plugins import apply_plugins
from tgcf.utils import send_message


class RandomMessageHandler:
    """Handles random message posting in live mode."""
    
    def __init__(self, client: TelegramClient):
        self.client = client
        self.is_running = False
        self.tasks: Dict[int, asyncio.Task] = {}
        
    async def start(self):
        """Start random message posting for all configured sources."""
        if not CONFIG.live.random_enabled:
            logging.info("Random message posting is disabled")
            return
            
        self.is_running = True
        logging.info("Starting random message handler")
        
        # Start tasks for each active source
        for source_str in CONFIG.live.random_active_sources:
            try:
                source_id = int(source_str) if source_str.lstrip('-').isdigit() else source_str
                source_id = await config.get_id(self.client, source_id)
                
                if source_id in config.from_to:
                    task = asyncio.create_task(self._random_poster_for_source(source_id))
                    self.tasks[source_id] = task
                    logging.info(f"Started random posting task for source {source_id}")
                else:
                    logging.warning(f"Source {source_id} not found in configured forwards")
                    
            except Exception as e:
                logging.error(f"Error starting random posting for source {source_str}: {e}")
    
    async def stop(self):
        """Stop all random message posting tasks."""
        self.is_running = False
        
        for source_id, task in self.tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                logging.info(f"Stopped random posting task for source {source_id}")
        
        self.tasks.clear()
        logging.info("Random message handler stopped")
    
    async def _random_poster_for_source(self, source_id: int):
        """Post random messages for a specific source."""
        try:
            total_posted = 0
            
            while self.is_running:
                # Check if we've reached the daily limit
                if CONFIG.live.random_total_limit > 0:
                    current_count = st.random_message_count.get(source_id, 0)
                    if current_count >= CONFIG.live.random_total_limit:
                        logging.info(f"Daily random message limit reached for source {source_id}")
                        break
                
                # Get random messages from the source
                messages = await self._get_random_messages(source_id, CONFIG.live.random_count)
                
                if not messages:
                    logging.warning(f"No messages found for random posting from source {source_id}")
                    await asyncio.sleep(CONFIG.live.random_delay)
                    continue
                
                # Post each message
                for message in messages:
                    if not self.is_running:
                        break
                        
                    try:
                        await self._post_random_message(source_id, message)
                        total_posted += 1
                        
                        # Update counter
                        if source_id not in st.random_message_count:
                            st.random_message_count[source_id] = 0
                        st.random_message_count[source_id] += 1
                        
                        logging.info(f"Posted random message from source {source_id}, total today: {st.random_message_count[source_id]}")
                        
                        # Check if we've reached the limit
                        if (CONFIG.live.random_total_limit > 0 and 
                            st.random_message_count[source_id] >= CONFIG.live.random_total_limit):
                            logging.info(f"Daily random message limit reached for source {source_id}")
                            return
                            
                    except Exception as e:
                        logging.error(f"Error posting random message from source {source_id}: {e}")
                
                # Wait before next batch
                if self.is_running:
                    logging.info(f"Waiting {CONFIG.live.random_delay} seconds before next random batch for source {source_id}")
                    await asyncio.sleep(CONFIG.live.random_delay)
                    
        except asyncio.CancelledError:
            logging.info(f"Random posting task cancelled for source {source_id}")
        except Exception as e:
            logging.error(f"Error in random poster for source {source_id}: {e}")
    
    async def _get_random_messages(self, source_id: int, count: int) -> List[Message]:
        """Get random messages from the source chat (Render-optimized)."""
        try:
            # Limit message fetching for Render's memory constraints
            messages = []
            used_ids = st.random_message_history.get(source_id, [])
            
            # Reduce message limit for Render (was 1000, now 300)
            message_limit = min(300, count * 20)  # More conservative approach
            
            batch_size = 50  # Process in smaller batches
            processed = 0
            
            async for message in self.client.iter_messages(source_id, limit=message_limit):
                if (isinstance(message, MessageService) or 
                    message.id in used_ids or 
                    not message.text or
                    len(message.text) > 1000):  # Skip very long messages to save memory
                    continue
                    
                messages.append(message)
                processed += 1
                
                # Process in batches to prevent memory spikes
                if processed % batch_size == 0:
                    await asyncio.sleep(0.1)  # Small delay to prevent CPU spikes
                
                # Break if we have enough candidates (reduced multiplier)
                if len(messages) >= count * 5:  # Reduced from 10x to 5x for Render
                    break
            
            if not messages:
                return []
            
            # Select random messages
            selected = random.sample(messages, min(count, len(messages)))
            
            # Track used message IDs
            if source_id not in st.random_message_history:
                st.random_message_history[source_id] = []
            
            for msg in selected:
                st.random_message_history[source_id].append(msg.id)
                
            # Keep only recent IDs to prevent memory bloat
            if len(st.random_message_history[source_id]) > 5000:
                st.random_message_history[source_id] = st.random_message_history[source_id][-2500:]
            
            return selected
            
        except Exception as e:
            logging.error(f"Error getting random messages from source {source_id}: {e}")
            return []
    
    async def _post_random_message(self, source_id: int, message: Message):
        """Post a random message to destinations."""
        try:
            # Get destinations for this source
            dest_data = config.from_to.get(source_id)
            if not dest_data:
                logging.warning(f"No destinations configured for source {source_id}")
                return
            
            destinations = dest_data.get("dests", [])
            watermark_text = dest_data.get("watermark_text", "")
            
            # Apply plugins to the message
            tm = await apply_plugins(message)
            if not tm:
                logging.warning("Message filtered out by plugins")
                return
            
            # Add watermark if configured
            if watermark_text:
                if tm.text:
                    tm.text = f"{tm.text}\n\n{watermark_text}"
                else:
                    tm.text = watermark_text
            
            # Add random message indicator
            random_indicator = "\n\n📱 Random from archive"
            if tm.text:
                tm.text = f"{tm.text}{random_indicator}"
            else:
                tm.text = random_indicator
            
            # Send to all destinations
            for dest in destinations:
                try:
                    await send_message(dest, tm)
                    logging.info(f"Successfully sent random message to destination {dest}")
                except Exception as e:
                    logging.error(f"Error sending random message to destination {dest}: {e}")
            
            tm.clear()
            
        except Exception as e:
            logging.error(f"Error posting random message: {e}")


def reset_daily_counters():
    """Reset daily random message counters."""
    st.random_message_count.clear()
    logging.info("Reset daily random message counters")


# Global instance
random_handler: Optional[RandomMessageHandler] = None
