import logging
from pathlib import Path

import streamlit as st

from rapport import tools
from rapport.chathistory import ChatHistoryManager
from rapport.chatgateway import ChatGateway
from rapport.chatmodel import PAGE_CHAT, PAGE_CONFIG, PAGE_HELP, PAGE_HISTORY
from rapport.appconfig import ConfigStore

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

st.set_page_config(
    page_title="Rapport",
    page_icon="images/rapport-favicon.png",
    layout="centered",
)
st.set_option("client.toolbarMode", "minimal")


base_dir = Path.home() / ".config" / "rapport"
base_dir.mkdir(exist_ok=True)


# Callbacks use switch_to_page to do navigation,
# as st.switch_path doesn't work from callbacks.
sp = st.session_state.get("switch_to_page", None)
if sp:
    del st.session_state["switch_to_page"]
    st.switch_page(sp)

st.logo(
    image="images/rapport-logo.png",
    size="large",
    icon_image="images/rapport-logo.png",
)
st.html("""
  <style>
    [alt=Logo] {
      height: 4rem;
    }
  </style>
        """)

pg = st.navigation(
    [
        st.Page(PAGE_CHAT, title="Chat", icon=":material/chat_bubble:"),
        st.Page(PAGE_HISTORY, title="History", icon=":material/history:"),
        st.Page(PAGE_CONFIG, title="Settings", icon=":material/settings:"),
        st.Page(PAGE_HELP, title="Help", icon=":material/help:"),
    ]
)


# with show_spinner=True, often get ghosted components because streamlit
# inserts a spinner element into the tree.
@st.cache_resource(show_spinner=False)
def gateway():
    print("Init chat gateway")
    return ChatGateway()


@st.cache_resource(show_spinner=False)
def history_store():
    return ChatHistoryManager(base_dir)


@st.cache_resource(show_spinner=False)
def config_store():
    return ConfigStore(base_dir / "config.json")


if "config_store" not in st.session_state:
    st.session_state["config_store"] = config_store()
if "history_manager" not in st.session_state:
    st.session_state["history_manager"] = history_store()
if "chat_gateway" not in st.session_state:
    st.session_state["chat_gateway"] = gateway()

tools.registry.initialise_tools(st.session_state["config_store"])

pg.run()
