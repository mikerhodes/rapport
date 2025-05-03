from typing import List, Dict

import streamlit as st

from rapport.chatmodel import PAGE_CHAT

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
    st.session_state["load_chat_with_id"] = chat_id
    st.session_state["switch_to_page"] = PAGE_CHAT


def edit_chat_title(chat_id, new_title):
    """Update the title of a chat"""
    if not new_title.strip():
        # Don't allow empty titles
        return

    history_manager = st.session_state["history_manager"]
    chat = history_manager.get_chat(chat_id)
    if chat:
        chat.title = new_title
        history_manager.save_chat(chat)

        # If this is the current chat, update it in session state too
        if (
            st.session_state.get("chat")
            and chat_id == st.session_state["chat"].id
        ):
            st.session_state["chat"].title = new_title


#
# Display page
#


@st.dialog("Edit chat title")
def handle_edit_dialog(chat_id, chat_title: str):
    new_title = st.text_input(
        "New title",
        value=chat_title,
    )
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Save", use_container_width=True):
            edit_chat_title(chat_id, new_title)
            st.rerun()
    with col2:
        if st.button("Cancel", use_container_width=True):
            st.rerun()


def main():
    st.html("""
        <style>
        div[class*="st-key-chat_chathistory-"]{}
         button {
            justify-content: left !important;
            text-align: left;
        }
        </style>
        """)
    st.title("History")

    recent_chats = st.session_state["history_manager"].get_recent_chats(
        limit=100
    )
    show_chat_history(recent_chats)


def show_chat_history(recent_chats: List[Dict]):
    day = None
    for chat in recent_chats:
        if day != chat["created_at"][:7]:
            st.subheader(chat["created_at"][:7])
            day = chat["created_at"][:7]

        col1, col2, col3 = st.columns([5, 0.5, 0.5])
        with col1:
            # Highlight current chat
            current_chat = st.session_state.get("chat", None)
            is_current_chat = current_chat and chat["id"] == current_chat.id
            st.button(
                chat["title"],
                key=f"chat_chathistory_{chat['id']}",
                on_click=load_chat,
                args=(chat["id"],),
                use_container_width=True,
                type="primary" if is_current_chat else "tertiary",
            )
        with col2:
            # Edit button
            if st.button(
                "",
                key=f"edit_chathistory_{chat['id']}",
                icon=":material/edit:",
                type="tertiary",
            ):
                handle_edit_dialog(chat["id"], chat["title"])
        with col3:
            # Delete button
            st.button(
                "",
                key=f"delete_chathistory_{chat['id']}",
                on_click=delete_chat,
                args=(chat["id"],),
                icon=":material/delete:",
                type="tertiary",
            )


if __name__ == "__main__":
    main()
