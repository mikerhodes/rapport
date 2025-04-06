import logging
from pathlib import Path

import streamlit as st

from rapport.chathistory import ChatHistoryManager
from rapport.chatgateway import ChatGateway
from rapport.chatmodel import PAGE_CHAT, PAGE_CONFIG, PAGE_HELP, PAGE_HISTORY
from rapport.appconfig import ConfigStore

logging.basicConfig(level=logging.INFO)

st.set_page_config(
    page_title="Rapport", page_icon=":robot_face:", layout="centered"
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
    image="images/logo.png", size="large", icon_image="images/logo-small.png"
)

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
    print("Init chat gateway")
    st.session_state["chat_gateway"] = gateway()


pg.run()
