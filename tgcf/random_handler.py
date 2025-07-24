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
from tgcf.forward_count import get_random_message_count, increment_random_message_count


class RandomMessageHandler:
    """Handles random message posting in live mode."""
    
    def __init__(self, client: TelegramClient):
        self.client = client
        self.is_running = False
        self.tasks: Dict[int, asyncio.Task] = {}
        self.random_states: Dict[int, Dict] = {}  # Store state for each source
        
    async def start(self):
        """Start random message posting for all configured sources."""
        if not CONFIG.live.random_enabled:
            logging.info("Random message posting is disabled")
            return
            
        self.is_running = True
        logging.info("Starting random message handler")
        
        # Load previous states and synchronize counters
        try:
            from tgcf.state_manager import get_state_manager
            state_manager = get_state_manager()
            
            for source_str in CONFIG.live.random_active_sources:
                source_id = int(source_str) if source_str.lstrip('-').isdigit() else source_str
                source_id = await config.get_id(self.client, source_id)
                
                # Synchronize in-memory counter with MongoDB counter
                current_count = get_random_message_count(source_id)
                st.random_message_count[source_id] = current_count
                logging.info(f"Synchronized counter for source {source_id}: {current_count} messages today")
                
                # Load previous state for this source
                prev_state = state_manager.load_random_message_state(source_id)
                if prev_state:
                    self.random_states[source_id] = prev_state
                    logging.info(f"Loaded previous state for source {source_id}")
                else:
                    # Initialize new state
                    self.random_states[source_id] = {
                        'last_random_time': None,
                        'random_count': current_count,
                        'total_sent': 0
                    }
        except Exception as e:
            logging.error(f"Error loading random states: {e}")
        
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
        
        # Start a periodic checker to restart stopped sources
        if self.tasks:
            checker_task = asyncio.create_task(self._periodic_limit_checker())
            self.tasks['_checker'] = checker_task
            logging.info("Started periodic limit checker")
    
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
                    from tgcf.forward_count import get_random_message_count
                    current_count = get_random_message_count(source_id)
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
                        
                        # Update counter for each message using both systems
                        increment_random_message_count(source_id)  # MongoDB counter
                        if source_id not in st.random_message_count:
                            st.random_message_count[source_id] = 0
                        st.random_message_count[source_id] += 1  # In-memory counter
                        
                        # Update state tracking
                        if source_id in self.random_states:
                            from datetime import datetime
                            self.random_states[source_id]['last_random_time'] = datetime.utcnow()
                            self.random_states[source_id]['random_count'] = st.random_message_count[source_id]
                            self.random_states[source_id]['total_sent'] = self.random_states[source_id].get('total_sent', 0) + 1
                        
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
    
    async def _periodic_limit_checker(self):
        """Periodically check if stopped sources can be restarted (e.g., after day change)."""
        try:
            while self.is_running:
                await asyncio.sleep(3600)  # Check every hour
                
                if not self.is_running:
                    break
                    
                logging.info("Running periodic limit check for stopped sources")
                
                # Check each configured source
                for source_str in CONFIG.live.random_active_sources:
                    try:
                        source_id = int(source_str) if source_str.lstrip('-').isdigit() else source_str
                        source_id = await config.get_id(self.client, source_id)
                        
                        # Skip if task is already running
                        if source_id in self.tasks and not self.tasks[source_id].done():
                            continue
                            
                        # Check if source should be active (under limit)
                        if CONFIG.live.random_total_limit > 0:
                            current_count = get_random_message_count(source_id)
                            if current_count < CONFIG.live.random_total_limit:
                                # Restart this source's task
                                logging.info(f"Restarting random posting for source {source_id} (count: {current_count}/{CONFIG.live.random_total_limit})")
                                
                                # Synchronize counter
                                st.random_message_count[source_id] = current_count
                                
                                if source_id in config.from_to:
                                    task = asyncio.create_task(self._random_poster_for_source(source_id))
                                    self.tasks[source_id] = task
                                    logging.info(f"Restarted random posting task for source {source_id}")
                        else:
                            # No limit, should always be running
                            if source_id in config.from_to:
                                task = asyncio.create_task(self._random_poster_for_source(source_id))
                                self.tasks[source_id] = task
                                logging.info(f"Restarted random posting task for source {source_id} (no limit)")
                                
                    except Exception as e:
                        logging.error(f"Error checking source {source_str} in periodic check: {e}")
                        
        except asyncio.CancelledError:
            logging.info("Periodic limit checker cancelled")
        except Exception as e:
            logging.error(f"Error in periodic limit checker: {e}")
    
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
            
            # Apply plugins to the message
            tm = await apply_plugins(message, dest_data)
            if not tm:
                logging.warning("Message filtered out by plugins")
                return
            
            # Add random message indicator
            random_indicator = "\n\n📱 @starteralinks"
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
