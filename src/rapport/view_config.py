import streamlit as st
from pydantic import TypeAdapter, ValidationError

from rapport import appglobals
from rapport import appconfig

st.title("Settings")

# Get config store from session state
config = appglobals.configstore.load_config()

# Create form for editing settings
with st.form("settings_form"):
    tab1, tab2, tab3 = st.tabs(["General", "Custom prompt", "MCP Servers"])
    with tab1:
        st.subheader("AI Model Configuration")

        # Display last used model as read-only information
        if config.last_used_model:
            st.markdown(f"Last used model: `{config.last_used_model}`")

        preferred_model = st.text_input(
            "Preferred model (leave blank to use last used)",
            value=config.preferred_model or "",
            placeholder="Enter your preferred AI model",
        )

        st.subheader("Obsidian integration")

        obsidian_directory = st.text_input(
            "Obsidian directory path (Save to Obsidian will use this path, likely it should be a subdirectory inside your vault)",
            value=config.obsidian_directory or "",
            placeholder="Enter your Obsidian vault directory path",
        )

    with tab2:
        st.subheader("Custom system prompt")
        custom_system_prompt = st.text_area(
            "Details you want the model to know about you:",
            value=config.custom_system_prompt or "",
            placeholder="Enter things about you (eg, 'I like Python') or customisations to the model's behaviour (eg, 'be sarcastic a lot')",
            height=300,
            help="Feel free to phrase this using 'I', such as 'I like cats'",
        )

    with tab3:
        st.subheader("MCP Servers")
        with st.expander("JSON configuration examples"):
            st.markdown("""
            Rapport only supports tools that support a
            HTTP interface. It uses JSON configuration
            to add each MCP server to Rapport. You must
            explicitly list the allowed tools.

            These configuration examples are for the
            mcphttp.py and mcpstdio.py examples that
            ship with Rapport.
            """)
            st.caption("Hover to copy to clipboard")
            st.json("""{
                "addmcp": {
                    "url": "http://127.0.0.1:9000/mcp/",
                    "allowed_tools": ["add","mul"]
                },
                "mcpstdio": {
                    "command": "uv",
                    "args": ["run","mcpstdio.py"],
                    "allowed_tools": ["download_url"]
                }
            }""")
        with st.expander("Currently loaded tools"):
            for t in appglobals.toolregistry.get_enabled_tools():
                st.markdown(f"`{t.name}` from `{t.server}`")
        ta = TypeAdapter(appconfig.MCPServerList)
        mcp_str = ta.dump_json(config.mcp_servers, indent=4).decode("utf-8")
        mcp_servers = st.text_area(
            "MCP JSON configuration",
            label_visibility="collapsed",
            value=mcp_str,
            placeholder="http://localhost:9000 add,multiple,divide",
            height=300,
        )

    # Submit button
    submitted = st.form_submit_button("Save Settings")

    if submitted:
        mcp = {}
        try:
            ta = TypeAdapter(appconfig.MCPServerList)
            mcp = ta.validate_json(mcp_servers if mcp_servers else "{}")
        except ValidationError as ex:
            # logger.error("Error saving configuration: %s", ex)
            st.error(f"Error validating MCP servers:\n\n{str(ex)}")

        # Update config with new values
        if mcp:
            new_config = appconfig.Config(
                preferred_model=preferred_model if preferred_model else None,
                obsidian_directory=obsidian_directory
                if obsidian_directory
                else None,
                last_used_model=config.last_used_model,
                custom_system_prompt=custom_system_prompt
                if custom_system_prompt
                else None,
                mcp_servers=mcp,
            )

            # Save to disk
            appglobals.configstore.save_config(new_config)
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
