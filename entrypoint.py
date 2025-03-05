from pathlib import Path
import streamlit as st

from chathistory import ChatHistoryManager
from chatgateway import ChatGateway
from chatmodel import PAGE_CHAT, PAGE_HISTORY
from appconfig import ConfigStore


base_dir = Path.home() / ".config" / "rapport"
base_dir.mkdir(exist_ok=True)


@st.cache_resource
def history() -> ChatHistoryManager:
    return ChatHistoryManager(base_dir)


@st.cache_resource
def gateway() -> ChatGateway:
    return ChatGateway()


@st.cache_resource
def config() -> ConfigStore:
    return ConfigStore(base_dir / "config.json")


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
    ]
)
st.set_page_config(
    page_title="Rapport", page_icon=":robot_face:", layout="wide"
)

# Not sure if the state is the right place for this,
# or whether the other parts of the app should just
# call the resouce_cache'd methods.
st.session_state["config_store"] = config()
st.session_state["history_manager"] = history()
st.session_state["chat_gateway"] = gateway()

pg.run()
