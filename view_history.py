from datetime import datetime

import streamlit as st

from chatmodel import PAGE_CHAT, Chat

#
# Helpers and handlers
#


def delete_chat(chat_id):
    """Delete a chat, starting a new chat if the deleted chat
    is currently the active chat"""
    st.session_state["history_manager"].delete_chat(chat_id)
    if (
        st.session_state.get("chat")
        and chat_id == st.session_state["chat"].id
    ):
        del st.session_state["chat"]


def load_chat(chat_id):
    """Load a chat from history"""
    chat = st.session_state["history_manager"].get_chat(chat_id)
    if chat:
        st.session_state["chat"] = Chat(
            id=chat_id,
            model=chat["model"],
            messages=chat["messages"],
            created_at=datetime.fromisoformat(chat["created_at"]),
        )
        st.session_state["switch_to_page"] = PAGE_CHAT


# Display recent chats
st.markdown("## History")
recent_chats = st.session_state["history_manager"].get_recent_chats(
    limit=100
)


for chat in recent_chats:
    col1, col2 = st.columns([6, 1])
    with col1:
        # Highlight current chat
        icon = None
        current_chat = st.session_state.get("chat", None)
        if current_chat and chat["id"] == current_chat.id:
            icon = ":material/edit:"
        b = st.button(
            chat["title"],
            key=f"chat_chathistory_{chat['id']}",
            on_click=load_chat,
            args=[chat["id"]],
            use_container_width=True,
            icon=icon,
        )
    with col2:
        st.button(
            "",
            key=f"delete_chathistory_{chat['id']}",
            on_click=delete_chat,
            args=[chat["id"]],
            icon=":material/delete:",
            type="tertiary",
        )
