"""Process manager for tgcf auto-restart functionality.

This module handles process management, monitoring, and auto-restart capabilities
to ensure the application can resume after server restarts or crashes.
"""

import os
import signal
import subprocess
import time
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from tgcf.config import CONFIG, read_config, write_config
from tgcf.state_manager import get_state_manager

# Try to import psutil, fallback if not available
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.warning("psutil not available, using basic process management")


class ProcessManager:
    """Manages tgcf processes with auto-restart capability."""
    
    def __init__(self):
        self.config = read_config()
        self.state_manager = get_state_manager()
        self.process: Optional[subprocess.Popen] = None
        self.last_restart_time = None
        self.restart_count = 0
        self.max_restarts = 10
        self.restart_delay = 30  # seconds
        
    def is_process_running(self, pid: int) -> bool:
        """Check if a process is actually running."""
        if pid == 0:
            return False
        
        if not PSUTIL_AVAILABLE:
            # Fallback method using os.kill
            try:
                os.kill(pid, 0)
                return True
            except (OSError, ProcessLookupError):
                return False
        
        try:
            # Check if process exists and is running
            process = psutil.Process(pid)
            return process.is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False
    
    def get_current_process_status(self) -> Dict[str, Any]:
        """Get current process status information."""
        config = read_config()
        pid = config.pid
        
        status = {
            "pid": pid,
            "is_running": self.is_process_running(pid),
            "restart_count": self.restart_count,
            "last_restart": self.last_restart_time
        }
        
        if pid != 0 and PSUTIL_AVAILABLE:
            try:
                process = psutil.Process(pid)
                status.update({
                    "name": process.name(),
                    "status": process.status(),
                    "cpu_percent": process.cpu_percent(),
                    "memory_percent": process.memory_percent(),
                    "create_time": datetime.fromtimestamp(process.create_time()).isoformat()
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                status["is_running"] = False
        
        return status
    
    def start_process(self, mode: str = "live", force: bool = False) -> bool:
        """Start the tgcf process."""
        config = read_config()
        
        # Check if process is already running
        if not force and config.pid != 0 and self.is_process_running(config.pid):
            logging.info(f"Process {config.pid} is already running")
            return True
        
        # Clean up old PID if process is not running
        if config.pid != 0 and not self.is_process_running(config.pid):
            logging.info(f"Cleaning up stale PID {config.pid}")
            config.pid = 0
            write_config(config)
        
        try:
            # Ensure logs directory exists
            log_dir = "/app/logs" if os.path.exists("/app") else "logs"
            os.makedirs(log_dir, exist_ok=True)
            log_file_path = os.path.join(log_dir, "tgcf.log")
            
            # Start the process
            with open(log_file_path, "w") as log_file:
                self.process = subprocess.Popen(
                    ["tgcf", "--loud", mode],
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    preexec_fn=os.setsid if os.name != 'nt' else None
                )
            
            # Update config with new PID
            config.pid = self.process.pid
            write_config(config)
            
            # Save process start information to state
            self.state_manager.save_application_state(
                mode=mode,
                config_hash=str(hash(str(config.dict()))),
                running_since=datetime.utcnow(),
                active_forwards=[]
            )
            
            self.last_restart_time = datetime.utcnow()
            self.restart_count += 1
            
            logging.info(f"Started tgcf process with PID {self.process.pid}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to start process: {e}")
            return False
    
    def stop_process(self, pid: Optional[int] = None) -> bool:
        """Stop the tgcf process."""
        config = read_config()
        target_pid = pid or config.pid
        
        if target_pid == 0:
            logging.info("No process to stop")
            return True
        
        try:
            if os.name == 'nt':  # Windows
                os.kill(target_pid, signal.SIGTERM)
            else:  # Unix-like systems
                os.killpg(os.getpgid(target_pid), signal.SIGTERM)
            
            # Wait for process to terminate
            time.sleep(2)
            
            # Force kill if still running
            if self.is_process_running(target_pid):
                if os.name == 'nt':
                    os.kill(target_pid, signal.SIGKILL)
                else:
                    os.killpg(os.getpgid(target_pid), signal.SIGKILL)
                time.sleep(1)
            
            # Clean up PID
            config.pid = 0
            write_config(config)
            
            # Mark session as ended
            self.state_manager.mark_session_ended("manual_stop")
            
            logging.info(f"Stopped process {target_pid}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to stop process {target_pid}: {e}")
            # Clean up PID anyway
            config.pid = 0
            write_config(config)
            return False
    
    def restart_process(self, mode: str = "live") -> bool:
        """Restart the tgcf process."""
        config = read_config()
        
        # Stop current process if running
        if config.pid != 0:
            self.stop_process(config.pid)
        
        # Wait a bit before restart
        time.sleep(self.restart_delay)
        
        # Start new process
        return self.start_process(mode)
    
    def auto_restart_if_needed(self) -> bool:
        """Check if process needs restart and restart if necessary."""
        config = read_config()
        
        if config.pid == 0:
            # No process configured, check if we should auto-start
            app_state = self.state_manager.load_application_state()
            if app_state and app_state.get('mode'):
                mode = app_state['mode']
                logging.info(f"Auto-starting tgcf in {mode} mode based on previous state")
                return self.start_process(mode)
            return False
        
        # Check if current process is running
        if not self.is_process_running(config.pid):
            logging.warning(f"Process {config.pid} is not running, attempting restart")
            
            # Check restart limits
            if self.restart_count >= self.max_restarts:
                logging.error(f"Max restart attempts ({self.max_restarts}) exceeded")
                return False
            
            # Load previous mode from state
            app_state = self.state_manager.load_application_state()
            mode = app_state.get('mode', 'live') if app_state else 'live'
            
            # Restart process
            return self.restart_process(mode)
        
        return True
    
    def monitor_process(self, interval: int = 60) -> None:
        """Monitor process and restart if needed."""
        logging.info(f"Starting process monitor with {interval}s interval")
        
        while True:
            try:
                self.auto_restart_if_needed()
                time.sleep(interval)
            except KeyboardInterrupt:
                logging.info("Process monitor stopped by user")
                break
            except Exception as e:
                logging.error(f"Error in process monitor: {e}")
                time.sleep(interval)
    
    def get_logs(self, lines: int = 100) -> str:
        """Get recent logs from the process."""
        log_dir = "/app/logs" if os.path.exists("/app") else "logs"
        log_file = os.path.join(log_dir, "tgcf.log")
        
        if not os.path.exists(log_file):
            return "No logs available"
        
        try:
            with open(log_file, "r") as f:
                all_lines = f.readlines()
                recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
                return "".join(recent_lines)
        except Exception as e:
            return f"Error reading logs: {e}"


# Global process manager instance
process_manager: Optional[ProcessManager] = None


def get_process_manager() -> ProcessManager:
    """Get or create the global process manager instance."""
    global process_manager
    
    if process_manager is None:
        process_manager = ProcessManager()
    
    return process_manager
