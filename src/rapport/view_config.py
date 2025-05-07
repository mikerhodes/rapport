import streamlit as st
from pathlib import Path

from rapport.appconfig import Config, ConfigStore

st.title("Settings")

# Get config store from session state
config_store = st.session_state["config_store"]
config = config_store.load_config()

# Create form for editing settings
with st.form("settings_form"):
    st.subheader("AI Model Configuration")

    # Display last used model as read-only information
    if config.last_used_model:
        st.markdown(f"Last used model: `{config.last_used_model}`")

    preferred_model = st.text_input(
        "Preferred model (leave blank to use last used)",
        value=config.preferred_model or "",
        placeholder="Enter your preferred AI model",
    )

    custom_system_prompt = st.text_area(
        "Details you want the model to know about you:",
        value=config.custom_system_prompt or "",
        placeholder="Enter things about you (eg, 'I like Python') or customisations to the model's behaviour (eg, 'be sarcastic a lot')",
        height=150,
        help="Feel free to phrase this using 'I', such as 'I like cats'",
    )

    st.subheader("Obsidian integration")

    obsidian_directory = st.text_input(
        "Obsidian directory path (Save to Obsidian will use this path, likely it should be a subdirectory inside your vault)",
        value=config.obsidian_directory or "",
        placeholder="Enter your Obsidian vault directory path",
    )

    # Submit button
    submitted = st.form_submit_button("Save Settings")

    if submitted:
        # Update config with new values
        new_config = Config(
            preferred_model=preferred_model if preferred_model else None,
            obsidian_directory=obsidian_directory
            if obsidian_directory
            else None,
            last_used_model=config.last_used_model,
            custom_system_prompt=custom_system_prompt
            if custom_system_prompt
            else None,
        )

        # Save to disk
        config_store.save_config(new_config)
        st.success("Settings saved successfully!")

# Add some helpful information
with st.expander("Help"):
    st.markdown("""
    **Configuration Options:**

    - **Preferred Model**: The default AI model to use for chats
    - **Custom System Prompt**: Override the default system prompt with your own
    - **Obsidian Directory**: Path to your Obsidian vault for integration

    Settings are stored in `~/.config/rapport/config.json`
    """)
