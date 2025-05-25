import logging
from importlib import resources

import streamlit as st

from rapport.chatmodel import PAGE_CHAT, PAGE_CONFIG, PAGE_HELP, PAGE_HISTORY

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s %(funcName)s] %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)

st.set_page_config(
    page_title="Rapport",
    page_icon=(
        resources.files("rapport.images") / "rapport-favicon.png"
    ).read_bytes(),
    layout="centered",
)
st.set_option("client.toolbarMode", "minimal")


# Callbacks use switch_to_page to do navigation,
# as st.switch_path doesn't work from callbacks.
sp = st.session_state.get("switch_to_page", None)
if sp:
    del st.session_state["switch_to_page"]
    st.switch_page(sp)

st.logo(
    image=(
        resources.files("rapport.images") / "rapport-logo.png"
    ).read_bytes(),
    size="large",
    icon_image=(
        resources.files("rapport.images") / "rapport-logo.png"
    ).read_bytes(),
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


pg.run()
