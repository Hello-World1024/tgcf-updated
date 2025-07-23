"""Random message handler for live mode."""

import asyncio
import logging
import random
import time
from datetime import datetime, timedelta
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
        self.random_states: Dict[int, Dict] = {}  # Store state for each source
        self.last_reset_date = None  # Track when counters were last reset
        self.daily_reset_task = None  # Task for daily reset
        
    async def start(self):
        """Start random message posting for all configured sources."""
        if not CONFIG.live.random_enabled:
            logging.info("Random message posting is disabled")
            return
            
        self.is_running = True
        logging.info("Starting random message handler")
        
        # Initialize daily counter management
        await self._initialize_daily_counters()
        
        # Load previous states if available
        try:
            from tgcf.state_manager import get_state_manager
            state_manager = get_state_manager()
            
            for source_str in CONFIG.live.random_active_sources:
                source_id = int(source_str) if source_str.lstrip('-').isdigit() else source_str
                source_id = await config.get_id(self.client, source_id)
                
                # Load previous state for this source
                prev_state = state_manager.load_random_message_state(source_id)
                if prev_state:
                    self.random_states[source_id] = prev_state
                    logging.info(f"Loaded previous state for source {source_id}")
                else:
                    # Initialize new state
                    self.random_states[source_id] = {
                        'last_random_time': None,
                        'random_count': 0,
                        'total_sent': 0
                    }
        except Exception as e:
            logging.error(f"Error loading random states: {e}")
        
        # Start daily reset task
        if self.daily_reset_task is None:
            self.daily_reset_task = asyncio.create_task(self._daily_reset_scheduler())
            logging.info("Started daily counter reset scheduler")
        
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
        
        # Stop daily reset task
        if self.daily_reset_task and not self.daily_reset_task.done():
            self.daily_reset_task.cancel()
            try:
                await self.daily_reset_task
            except asyncio.CancelledError:
                pass
            logging.info("Stopped daily reset scheduler")
        
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
                # Check for daily reset before checking limits
                await self._check_and_reset_daily_counters()
                
                # Check if we've reached the daily limit
                if CONFIG.live.random_total_limit > 0:
                    current_count = self._get_daily_count(source_id)
                    if current_count >= CONFIG.live.random_total_limit:
                        logging.info(f"Daily random message limit reached for source {source_id} (count: {current_count})")
                        # Wait longer when limit is reached, but keep checking for daily reset
                        await asyncio.sleep(min(CONFIG.live.random_delay, 3600))  # Wait max 1 hour
                        continue
                
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
                        
                        # Update counter for each message (with date tracking)
                        self._increment_daily_count(source_id)
                        
                        # Update state tracking
                        if source_id in self.random_states:
                            self.random_states[source_id]['last_random_time'] = datetime.utcnow()
                            self.random_states[source_id]['random_count'] = self._get_daily_count(source_id)
                            self.random_states[source_id]['total_sent'] = self.random_states[source_id].get('total_sent', 0) + 1
                        
                        current_count = self._get_daily_count(source_id)
                        logging.info(f"Posted random message from source {source_id}, total today: {current_count}")
                        
                        # Check if we've reached the limit
                        if (CONFIG.live.random_total_limit > 0 and 
                            current_count >= CONFIG.live.random_total_limit):
                            logging.info(f"Daily random message limit reached for source {source_id}")
                            break  # Break inner loop to continue with delay and reset check
                            
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


    async def _initialize_daily_counters(self):
        """Initialize daily counter management."""
        try:
            current_date = datetime.now().date()
            
            # Initialize date tracking in storage if not exists
            if not hasattr(st, 'random_message_dates'):
                st.random_message_dates = {}
            
            # Check if we need to reset counters (new day)
            if (not hasattr(st, 'last_counter_reset_date') or 
                st.last_counter_reset_date != current_date):
                
                logging.info(f"Initializing daily counters for date: {current_date}")
                st.random_message_count.clear()
                st.random_message_dates.clear()
                st.last_counter_reset_date = current_date
                
                # Save reset state to MongoDB
                try:
                    from tgcf.state_manager import get_state_manager
                    state_manager = get_state_manager()
                    state_manager.save_state("daily_reset", {
                        "last_reset_date": current_date.isoformat(),
                        "reset_timestamp": datetime.now().isoformat()
                    })
                except Exception as e:
                    logging.warning(f"Could not save reset state to MongoDB: {e}")
                
            self.last_reset_date = current_date
            logging.info(f"Daily counter system initialized for {current_date}")
            
        except Exception as e:
            logging.error(f"Error initializing daily counters: {e}")
    
    async def _daily_reset_scheduler(self):
        """Background task to handle daily counter resets."""
        while self.is_running:
            try:
                current_time = datetime.now()
                current_date = current_time.date()
                
                # Calculate time until next midnight
                next_midnight = datetime.combine(current_date + timedelta(days=1), datetime.min.time())
                seconds_until_midnight = (next_midnight - current_time).total_seconds()
                
                # Wait until midnight (or check every hour if it's more than an hour away)
                sleep_time = min(seconds_until_midnight, 3600)  # Check at least every hour
                
                logging.debug(f"Daily reset scheduler: sleeping for {sleep_time:.0f} seconds")
                await asyncio.sleep(sleep_time)
                
                # Check if date has changed
                await self._check_and_reset_daily_counters()
                
            except asyncio.CancelledError:
                logging.info("Daily reset scheduler cancelled")
                break
            except Exception as e:
                logging.error(f"Error in daily reset scheduler: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes before retrying
    
    async def _check_and_reset_daily_counters(self):
        """Check if daily counters need to be reset."""
        try:
            current_date = datetime.now().date()
            
            if (not hasattr(st, 'last_counter_reset_date') or 
                st.last_counter_reset_date != current_date):
                
                logging.info(f"Daily reset triggered! Resetting counters for new date: {current_date}")
                
                # Reset all counters
                old_count = len(st.random_message_count)
                st.random_message_count.clear()
                
                if hasattr(st, 'random_message_dates'):
                    st.random_message_dates.clear()
                else:
                    st.random_message_dates = {}
                
                st.last_counter_reset_date = current_date
                self.last_reset_date = current_date
                
                logging.info(f"✅ Daily counters reset! Cleared {old_count} source counters for new date: {current_date}")
                
                # Save reset state to MongoDB
                try:
                    from tgcf.state_manager import get_state_manager
                    state_manager = get_state_manager()
                    state_manager.save_state("daily_reset", {
                        "last_reset_date": current_date.isoformat(),
                        "reset_timestamp": datetime.now().isoformat(),
                        "sources_reset": old_count
                    })
                    
                    # Force save empty counters
                    state_manager.save_state("random_counters", {
                        "date": current_date.isoformat(),
                        "counters": {},
                        "last_updated": datetime.now().isoformat()
                    })
                    
                except Exception as e:
                    logging.warning(f"Could not save reset state to MongoDB: {e}")
                    
        except Exception as e:
            logging.error(f"Error checking/resetting daily counters: {e}")
    
    def _get_daily_count(self, source_id: int) -> int:
        """Get the current daily count for a source with date validation."""
        try:
            current_date = datetime.now().date()
            
            # If date tracking doesn't exist, initialize it
            if not hasattr(st, 'random_message_dates'):
                st.random_message_dates = {}
            
            # Check if this source has a recorded date
            recorded_date = st.random_message_dates.get(source_id)
            
            # If no date recorded or date is old, reset this source's counter
            if recorded_date != current_date:
                st.random_message_count[source_id] = 0
                st.random_message_dates[source_id] = current_date
                return 0
            
            return st.random_message_count.get(source_id, 0)
            
        except Exception as e:
            logging.error(f"Error getting daily count for source {source_id}: {e}")
            return 0
    
    def _increment_daily_count(self, source_id: int):
        """Increment the daily count for a source with date tracking."""
        try:
            current_date = datetime.now().date()
            
            # Initialize if needed
            if not hasattr(st, 'random_message_dates'):
                st.random_message_dates = {}
            
            # Reset counter if date is old
            recorded_date = st.random_message_dates.get(source_id)
            if recorded_date != current_date:
                st.random_message_count[source_id] = 0
                st.random_message_dates[source_id] = current_date
            
            # Increment counter
            if source_id not in st.random_message_count:
                st.random_message_count[source_id] = 0
            st.random_message_count[source_id] += 1
            st.random_message_dates[source_id] = current_date
            
        except Exception as e:
            logging.error(f"Error incrementing daily count for source {source_id}: {e}")


def reset_daily_counters():
    """Manual reset of daily random message counters (for web UI button)."""
    try:
        current_date = datetime.now().date()
        old_count = len(st.random_message_count) if hasattr(st, 'random_message_count') else 0
        
        st.random_message_count.clear()
        
        if not hasattr(st, 'random_message_dates'):
            st.random_message_dates = {}
        st.random_message_dates.clear()
        st.last_counter_reset_date = current_date
        
        logging.info(f"Manual reset: Cleared {old_count} random message counters for date {current_date}")
        
        # Save to MongoDB
        try:
            from tgcf.state_manager import get_state_manager
            state_manager = get_state_manager()
            state_manager.save_state("manual_reset", {
                "reset_date": current_date.isoformat(),
                "reset_timestamp": datetime.now().isoformat(),
                "sources_reset": old_count,
                "reset_type": "manual"
            })
        except Exception as e:
            logging.warning(f"Could not save manual reset state: {e}")
            
    except Exception as e:
        logging.error(f"Error in manual daily counter reset: {e}")


# Global instance
random_handler: Optional[RandomMessageHandler] = None
