import logging
from pathlib import Path

import streamlit as st

from rapport.chathistory import ChatHistoryManager
from rapport.chatgateway import ChatGateway
from rapport.chatmodel import PAGE_CHAT, PAGE_CONFIG, PAGE_HISTORY
from rapport.appconfig import ConfigStore

logging.basicConfig(level=logging.INFO)

st.set_page_config(
    page_title="Rapport", page_icon=":robot_face:", layout="wide"
)


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
    ]
)
# TODO: why, when I put any of these into @st.cache_resource,
# does the first chat message of the first chat in a session
# end up with stale components outside the sidebar?
# More specifically, I think that the first rerun ends up with
# the stale components, as that rerun is the first after the cache_resource.
# So for now these remain created per session to avoid ugliness.
if "config_store" not in st.session_state:
    st.session_state["config_store"] = ConfigStore(base_dir / "config.json")
if "history_manager" not in st.session_state:
    ch = ChatHistoryManager(base_dir)
    st.session_state["history_manager"] = ch
if "chat_gateway" not in st.session_state:
    print("Init chat gateway")
    st.session_state["chat_gateway"] = ChatGateway()


@st.cache_resource
def foo():
    return "bar"


foo()


pg.run()
