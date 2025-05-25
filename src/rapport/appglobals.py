"""
We need to hang a few global service classes somewhere.

- Config
- ChatGateways
- ChatHistoryStore

That kind of thing --- things that get shared throughout
the application, but are not specific to the Streamlit
UI and so it's a bit awkward to put them in Streamlit
state.
"""

from pathlib import Path

from rapport.appconfig import ConfigStore
from rapport.chatgateway.chatgateway import ChatGateway
from rapport.chathistory import ChatHistoryStore
from rapport.tools import ToolRegistry

base_dir = Path.home() / ".config" / "rapport"
base_dir.mkdir(exist_ok=True)


configstore = ConfigStore(base_dir / "config.json")
chatstore = ChatHistoryStore(base_dir)
toolregistry = ToolRegistry()
chatgateway = ChatGateway()

__all__ = ["configstore", "chatstore", "toolregistry", "chatgateway"]
