from pathlib import Path
import streamlit as st

from chathistory import ChatHistoryManager
from chatgateway import ChatGateway
from chatmodel import PAGE_CHAT, PAGE_HISTORY
from appconfig import ConfigStore


base_dir = Path.home() / ".interlocution"
base_dir.mkdir(exist_ok=True)

if "config_store" not in st.session_state:
    st.session_state["config_store"] = ConfigStore(base_dir / "config.json")


# Initialize the chat history manager
if "history_manager" not in st.session_state:
    ch = ChatHistoryManager(base_dir)
    ch.clear_old_chats()  # clear on startup
    st.session_state["history_manager"] = ch

if "chat_gateway" not in st.session_state:
    print("Init chat gateway")
    st.session_state["chat_gateway"] = ChatGateway()

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
    page_title="Interlocution", page_icon=":robot_face:", layout="wide"
)
pg.run()
