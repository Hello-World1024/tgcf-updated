import json

import streamlit as st

from tgcf.config import CONFIG_FILE_NAME, read_config, write_config
from tgcf.utils import platform_info
from tgcf.web_ui.password import check_password
from tgcf.web_ui.utils import hide_st, switch_theme

CONFIG = read_config()

st.set_page_config(
    page_title="Advanced",
    page_icon="🔬",
)
hide_st(st)
switch_theme(st,CONFIG)

if check_password(st):

    st.warning("This page is for developers and advanced users.")
    if st.checkbox("I agree"):

        with st.expander("Version & Platform"):
            st.code(platform_info())

        with st.expander("Configuration"):
            with open(CONFIG_FILE_NAME, "r") as file:
                data = json.loads(file.read())
                dumped = json.dumps(data, indent=3)
            st.download_button(
                f"Download config json", data=dumped, file_name=CONFIG_FILE_NAME
            )
            st.json(data)

        with st.expander("Special Options for Live Mode"):
            CONFIG.live.sequential_updates = st.checkbox(
                "Enforce sequential updates", value=CONFIG.live.sequential_updates
            )

            CONFIG.live.delete_on_edit = st.text_input(
                "Delete a message when source edited to",
                value=CONFIG.live.delete_on_edit,
            )
            st.write(
                "When you edit the message in source to something particular, the message will be deleted in both source and destinations."
            )
            if st.checkbox("Customize Bot Messages"):
                st.info(
                    "Note: For userbots, the commands start with `.` instead of `/`, like `.start` and not `/start`"
                )
                CONFIG.bot_messages.start = st.text_area(
                    "Bot's Reply to /start command", value=CONFIG.bot_messages.start
                )
                CONFIG.bot_messages.bot_help = st.text_area(
                    "Bot's Reply to /help command", value=CONFIG.bot_messages.bot_help
                )

        with st.expander("Random Message Posting (Live Mode)"):
            st.write("Post random messages from past in live mode with configurable delay")
            st.info("This feature works parallel to normal live forwarding and is independent of 'Forwards per day' limit")
            
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
                st.write("Choose which source chats should have random message posting enabled")
                
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
                
                if st.button("Reset Daily Random Counters"):
                    from tgcf.random_handler import reset_daily_counters
                    reset_daily_counters()
                    st.success("Daily random message counters reset successfully!")
        
        if st.button("Save"):
            write_config(CONFIG)
