#!/usr/bin/env python3
"""Auto-start service for tgcf.

This module automatically starts tgcf processes on container restart
based on previously saved state.
"""

import os
import sys
import time
import logging
import threading
from datetime import datetime, timedelta
from tgcf.state_manager import get_state_manager
from tgcf.process_manager import get_process_manager
from tgcf.config import read_config


# Set up logging - will be configured later when service starts
logger = logging.getLogger(__name__)


class AutoStartService:
    """Service to automatically start tgcf processes on container restart."""
    
    def __init__(self):
        self.state_manager = get_state_manager()
        self.process_manager = get_process_manager()
        self.check_interval = 30  # Check every 30 seconds
        self.max_startup_wait = 300  # Wait max 5 minutes for MongoDB connection
        self.running = False
        
    def wait_for_dependencies(self):
        """Wait for MongoDB and other dependencies to be ready."""
        logger.info("Waiting for dependencies to be ready...")
        
        start_time = time.time()
        while time.time() - start_time < self.max_startup_wait:
            try:
                # Test MongoDB connection
                state = self.state_manager.load_application_state()
                logger.info("Dependencies are ready")
                return True
            except Exception as e:
                logger.debug(f"Dependencies not ready yet: {e}")
                time.sleep(5)
        
        logger.error("Dependencies not ready after waiting")
        return False
    
    def should_auto_start(self):
        """Check if we should automatically start tgcf."""
        try:
            # Check if there's a previous session that was running
            app_state = self.state_manager.load_application_state()
            if not app_state:
                logger.info("No previous session found")
                return False, None
            
            # Check if the session ended gracefully
            sessions = self.state_manager.get_all_sessions()
            if not sessions:
                logger.info("No sessions found")
                return False, None
            
            latest_session = sessions[0]  # Most recent session
            
            # Check if the latest session has an end reason
            session_data = self.state_manager.state_collection.find_one({
                "session_id": latest_session['session_id'],
                "session_ended": {"$exists": True}
            })
            
            if session_data:
                end_reason = session_data.get('end_reason', '')
                if end_reason in ['manual_stop', 'normal_shutdown']:
                    logger.info(f"Previous session ended gracefully: {end_reason}")
                    return False, None
                else:
                    logger.info(f"Previous session ended unexpectedly: {end_reason}")
                    return True, app_state.get('mode', 'live')
            else:
                # No end marker found, likely crashed
                logger.info("Previous session has no end marker, likely crashed")
                return True, app_state.get('mode', 'live')
                
        except Exception as e:
            logger.error(f"Error checking auto-start condition: {e}")
            return False, None
    
    def start_tgcf_if_needed(self):
        """Start tgcf if it should be auto-started."""
        try:
            config = read_config()
            
            # Check if already running
            if config.pid != 0 and self.process_manager.is_process_running(config.pid):
                logger.info(f"tgcf is already running with PID {config.pid}")
                return True
            
            # Check if we should auto-start
            should_start, mode = self.should_auto_start()
            if not should_start:
                logger.info("Auto-start not needed")
                return False
            
            logger.info(f"Auto-starting tgcf in {mode} mode")
            
            # Start the process
            if self.process_manager.start_process(mode, force=True):
                logger.info(f"Successfully auto-started tgcf in {mode} mode")
                return True
            else:
                logger.error("Failed to auto-start tgcf")
                return False
                
        except Exception as e:
            logger.error(f"Error during auto-start: {e}")
            return False
    
    def monitor_loop(self):
        """Main monitoring loop."""
        logger.info("Starting auto-start monitor loop")
        
        # Initial auto-start attempt
        time.sleep(10)  # Wait a bit for system to stabilize
        self.start_tgcf_if_needed()
        
        # Continue monitoring
        while self.running:
            try:
                # Check if process died and needs restart
                self.process_manager.auto_restart_if_needed()
                
                # Sleep before next check
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                time.sleep(self.check_interval)
    
    def start(self):
        """Start the auto-start service."""
        if self.running:
            logger.warning("Auto-start service is already running")
            return
        
        logger.info("Starting auto-start service")
        
        # Wait for dependencies
        if not self.wait_for_dependencies():
            logger.error("Failed to start auto-start service: dependencies not ready")
            return
        
        # Start monitoring in background thread
        self.running = True
        monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        monitor_thread.start()
        
        logger.info("Auto-start service started")
    
    def stop(self):
        """Stop the auto-start service."""
        logger.info("Stopping auto-start service")
        self.running = False


# Global service instance
auto_start_service = None


def get_auto_start_service():
    """Get the global auto-start service instance."""
    global auto_start_service
    if auto_start_service is None:
        auto_start_service = AutoStartService()
    return auto_start_service


def start_auto_start_service():
    """Start the auto-start service."""
    service = get_auto_start_service()
    service.start()


if __name__ == "__main__":
    # Run as standalone service
    os.makedirs('/app/logs', exist_ok=True)
    service = AutoStartService()
    service.start()
    
    try:
        # Keep the service running
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Shutting down auto-start service")
        service.stop()
