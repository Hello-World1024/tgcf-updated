import os
import signal
import subprocess
import time
from datetime import datetime

import streamlit as st

from tgcf.config import CONFIG, read_config, write_config
from tgcf.web_ui.password import check_password
from tgcf.web_ui.utils import hide_st, switch_theme
from tgcf.process_manager import get_process_manager
from tgcf.state_manager import get_state_manager

CONFIG = read_config()


def termination():
    st.code("process terminated!")
    os.rename("logs.txt", "old_logs.txt")
    with open("old_logs.txt", "r") as f:
        st.download_button(
            "Download last logs", data=f.read(), file_name="tgcf_logs.txt"
        )

    CONFIG = read_config()
    CONFIG.pid = 0
    write_config(CONFIG)
    st.button("Refresh page")


st.set_page_config(
    page_title="Run",
    page_icon="🏃",
)
hide_st(st)
switch_theme(st,CONFIG)
if check_password(st):
    with st.expander("Configure Run"):
        CONFIG.show_forwarded_from = st.checkbox(
            "Show 'Forwarded from'", value=CONFIG.show_forwarded_from
        )
        mode = st.radio("Choose mode", ["live", "past"], index=CONFIG.mode)
        if mode == "past":
            CONFIG.mode = 1
            st.warning(
                "Only User Account can be used in Past mode. Telegram does not allow bot account to go through history of a chat!"
            )
            CONFIG.past.delay = st.slider(
                "Delay in seconds", 0, 100, value=CONFIG.past.delay
            )
        else:
            CONFIG.mode = 0
            CONFIG.live.delete_sync = st.checkbox(
                "Sync when a message is deleted", value=CONFIG.live.delete_sync
            )

            # Random Message Posting Settings
            st.subheader("Random Message Posting")
            st.write("Post random messages from past in live mode (works parallel to normal forwarding)")

            CONFIG.live.random_enabled = st.checkbox(
                "Enable Random Message Posting",
                value=CONFIG.live.random_enabled,
                help="Enable posting random messages from source chats in live mode"
            )

            if CONFIG.live.random_enabled:
                col1, col2 = st.columns(2)

                with col1:
                    CONFIG.live.random_delay = st.number_input(
                        "Delay Between Batches (seconds)",
                        value=CONFIG.live.random_delay,
                        min_value=60,
                        max_value=86400,
                        help="Time to wait between posting random message batches"
                    )

                    CONFIG.live.random_count = st.number_input(
                        "Messages Per Batch",
                        value=CONFIG.live.random_count,
                        min_value=1,
                        max_value=50,
                        help="Number of random messages to post in each batch"
                    )

                with col2:
                    CONFIG.live.random_total_limit = st.number_input(
                        "Daily Random Message Limit",
                        value=CONFIG.live.random_total_limit,
                        min_value=0,
                        help="Maximum random messages per day per source (0 for unlimited)"
                    )

                st.write("**Select Source Chats for Random Posting:**")

                # Get available sources from forwards
                available_sources = []
                for forward in CONFIG.forwards:
                    if forward.use_this and forward.source:
                        available_sources.append(str(forward.source))

                if available_sources:
                    selected_sources = st.multiselect(
                        "Active Sources for Random Posting",
                        options=available_sources,
                        default=[s for s in CONFIG.live.random_active_sources if s in available_sources],
                        help="Select which source chats should post random messages"
                    )
                    CONFIG.live.random_active_sources = selected_sources
                else:
                    st.warning("No active forward connections found. Please configure connections first.")
                    CONFIG.live.random_active_sources = []

                st.info("💡 Tip: Random messages are independent of 'Forwards per day' limit and work parallel to normal forwarding")

        if st.button("Save"):
            write_config(CONFIG)

    # Initialize process manager
    process_manager = get_process_manager()
    state_manager = get_state_manager()
    
    # Get current process status
    process_status = process_manager.get_current_process_status()
    
    # Auto-restart functionality
    st.subheader("Process Management")
    
    # Show current status
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if process_status['is_running']:
            st.success(f"✅ Running (PID: {process_status['pid']})")
        else:
            st.error("❌ Not Running")
    
    with col2:
        if process_status['last_restart']:
            st.info(f"Last Start: {process_status['last_restart']}")
        else:
            st.info("Never Started")
    
    with col3:
        st.info(f"Restart Count: {process_status['restart_count']}")
    
    # Auto-restart on page load if needed
    if not process_status['is_running'] and CONFIG.pid == 0:
        app_state = state_manager.load_application_state()
        if app_state and app_state.get('mode'):
            if st.button("🔄 Auto-Resume from Previous Session", type="secondary"):
                mode_to_resume = app_state['mode']
                if process_manager.start_process(mode_to_resume):
                    st.success(f"Resumed tgcf in {mode_to_resume} mode")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Failed to resume process")
    
    # Manual controls
    if not process_status['is_running']:
        if st.button("▶️ Start", type="primary"):
            if process_manager.start_process(mode):
                st.success(f"Started tgcf in {mode} mode")
                time.sleep(2)
                st.rerun()
            else:
                st.error("Failed to start process")
    else:
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("⏹️ Stop", type="primary"):
                if process_manager.stop_process():
                    st.success("Process stopped successfully")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Failed to stop process")
        
        with col2:
            if st.button("🔄 Restart", type="secondary"):
                if process_manager.restart_process(mode):
                    st.success(f"Process restarted in {mode} mode")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Failed to restart process")
    
    # Show process details if running
    if process_status['is_running']:
        st.subheader("Process Details")
        
        if 'cpu_percent' in process_status:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("CPU Usage", f"{process_status['cpu_percent']:.1f}%")
            
            with col2:
                st.metric("Memory Usage", f"{process_status['memory_percent']:.1f}%")
            
            with col3:
                st.metric("Status", process_status['status'])
        else:
            st.info("Basic process monitoring (psutil not available)")
            st.write(f"**PID:** {process_status['pid']}")
            st.write(f"**Status:** Running")
    
    # Show session information
    if st.expander("Session Information"):
        sessions = state_manager.get_all_sessions()
        if sessions:
            st.subheader("Recent Sessions")
            for i, session in enumerate(sessions[:5]):
                with st.container():
                    st.write(f"**Session {i+1}:** {session['session_id']}")
                    st.write(f"Last Activity: {session['last_activity']}")
                    st.write(f"State Types: {', '.join(session['state_types'])}")
                    st.write("---")
        else:
            st.info("No previous sessions found")

    # Show logs section
    st.subheader("Logs")
    
    # Get logs from process manager
    try:
        lines = st.slider(
            "Lines of logs to show", min_value=50, max_value=500, step=50, value=100
        )
        
        logs_content = process_manager.get_logs(lines)
        if logs_content and logs_content != "No logs available":
            st.code(logs_content)
        else:
            st.info("No logs available yet. Start the process to see logs.")
            
        # Auto-refresh logs
        if st.button("🔄 Refresh Logs"):
            st.rerun()
            
        # Download logs
        if logs_content and logs_content != "No logs available":
            st.download_button(
                "📥 Download Logs",
                data=logs_content,
                file_name=f"tgcf_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain"
            )
            
    except Exception as e:
        st.error(f"Error loading logs: {e}")
