import os
import signal
import subprocess
import time

import streamlit as st

from tgcf.config import CONFIG, read_config, write_config
from tgcf.web_ui.password import check_password
from tgcf.web_ui.utils import hide_st, switch_theme

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

    check = False

    if CONFIG.pid == 0:
        check = st.button("Run", type="primary")

    if CONFIG.pid != 0:
        st.warning(
            "You must click stop and then re-run tgcf to apply changes in config."
        )
        # check if process is running using pid
        try:
            os.kill(CONFIG.pid, signal.SIGCONT)
        except Exception as err:
            st.code("The process has stopped.")
            st.code(err)
            CONFIG.pid = 0
            write_config(CONFIG)
            time.sleep(1)
            st.rerun()

        stop = st.button("Stop", type="primary")
        if stop:
            try:
                os.kill(CONFIG.pid, signal.SIGSTOP)
            except Exception as err:
                st.code(err)

                CONFIG.pid = 0
                write_config(CONFIG)
                st.button("Refresh Page")

            else:
                termination()

    if check:
        with open("logs.txt", "w") as logs:
            process = subprocess.Popen(
                ["tgcf", "--loud", mode],
                stdout=logs,
                stderr=subprocess.STDOUT,
            )
        CONFIG.pid = process.pid
        write_config(CONFIG)
        time.sleep(2)

        st.rerun()

    try:
        lines = st.slider(
            "Lines of logs to show", min_value=100, max_value=1000, step=100
        )
        temp_logs = "logs_n_lines.txt"
        os.system(f"rm {temp_logs}")
        with open("logs.txt", "r") as file:
            pass

        os.system(f"tail -n {lines} logs.txt >> {temp_logs}")
        with open(temp_logs, "r") as file:
            st.code(file.read())
    except FileNotFoundError as err:
        st.write("No present logs found")
    st.button("Load more logs")
