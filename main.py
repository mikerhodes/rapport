from io import StringIO
from textwrap import dedent

import ollama
import streamlit as st

from chathistory import ChatHistoryManager

PREFERRED_MODEL = "phi4:latest"

#
# initialize state
#


# Don't generate a chat message until the user has prompted
if "generate_assistant" not in st.session_state:
    st.session_state["generate_assistant"] = False

# Initialize the chat history manager
if "history_manager" not in st.session_state:
    st.session_state["history_manager"] = ChatHistoryManager()

with open("systemprompt.md", "r") as file:
    system_prompt = file.read()
SYSTEM = {
    "role": "system",
    "content": system_prompt,
}

# Message history
if "messages" not in st.session_state:
    st.session_state["messages"] = [SYSTEM]

if "current_chat_id" not in st.session_state:
    st.session_state["current_chat_id"] = None

# Retrieve the current models from ollama
# Set a preferred model as default if there's none set
models = [model["model"] for model in ollama.list()["models"]]
if "model" not in st.session_state and PREFERRED_MODEL in models:
    st.session_state["model"] = PREFERRED_MODEL

#
# Helpers
#


def clear_chat():
    """Clears the existing chat session"""
    st.session_state["messages"] = [SYSTEM]
    st.session_state["current_chat_id"] = None
    st.success("Chat cleared!", icon="✅")


def stream_model_response():
    """Returns a generator that yields chunks of the models respose"""
    response = ollama.chat(
        model=st.session_state["model"],
        messages=st.session_state["messages"],
        stream=True,
    )
    for chunk in response:
        yield chunk["message"]["content"]


def regenerate_last_response():
    """Regenerate the last assistant response"""
    # Remove the last assistant message
    st.session_state["messages"] = st.session_state["messages"][:-1]
    st.session_state["generate_assistant"] = True


#
# Chat history
#


def generate_chat_title():
    """Generate a title from the first 6 words of the first user message"""
    # Find first user message
    user_messages = [
        msg for msg in st.session_state["messages"] if msg["role"] == "user"
    ]
    if not user_messages:
        return "New Chat"

    # Take first 6 words of first message
    first_message = user_messages[0]["content"]
    words = first_message.split()[:6]
    title = " ".join(words)

    # Add ellipsis if we truncated the message
    if len(words) < len(first_message.split()):
        title += "..."

    return title


def save_current_chat():
    """Save the current chat session"""
    if len(st.session_state["messages"]) > 1:  # More than just system message
        title = generate_chat_title()
        chat_id = st.session_state["history_manager"].save_chat(
            st.session_state["messages"],
            title,
            st.session_state["model"],
            st.session_state["current_chat_id"],
        )
        st.session_state["current_chat_id"] = chat_id
        st.success("Chat saved successfully!", icon="✅")
    else:
        st.warning("Nothing to save - chat is empty!", icon="⚠️")


def load_chat(chat_id):
    """Load a chat from history"""
    chat = st.session_state["history_manager"].get_chat(chat_id)
    if chat:
        st.session_state["messages"] = chat["messages"]
        st.session_state["model"] = chat["model"]
        st.session_state["current_chat_id"] = chat_id


def delete_chat(chat_id):
    st.session_state["history_manager"].delete_chat(chat_id)
    if chat_id == st.session_state["current_chat_id"]:
        clear_chat()


#
# Start rendering the app
#

st.set_page_config(page_title="OllamaChat", page_icon=":robot_face:", layout="wide")

with st.sidebar:
    "## Configuration"
    st.selectbox("Choose your model", models, key="model")
    "## Ollama Python Chatbot"
    col1, col2 = st.columns(2)
    with col1:
        st.button("New Chat", on_click=clear_chat)
    with col2:
        st.button("Save Chat", on_click=save_current_chat)
    # Display recent chats
    st.markdown("## Recent Chats")
    recent_chats = st.session_state["history_manager"].get_recent_chats()

    for chat in recent_chats:
        col1, col2 = st.columns([4, 1])
        with col1:
            # Highlight current chat
            title = chat["title"]
            if chat["id"] == st.session_state["current_chat_id"]:
                title = f"📍 {title}"
            st.button(
                title, key=f"chat_{chat['id']}", on_click=load_chat, args=[chat["id"]]
            )
        with col2:
            st.button(
                "🗑️", key=f"delete_{chat['id']}", on_click=delete_chat, args=[chat["id"]]
            )

chat_col, col2 = st.columns([3, 1])
with chat_col:
    # Display chat messages from history on app rerun
    for message in st.session_state["messages"]:
        if message["role"] == "system":
            with st.expander("View system prompt"):
                st.markdown(message["content"])
        else:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
with col2:
    uploaded_file = st.file_uploader("Upload a plain text document")
    summarise_code = st.toggle("Upload is code")
    st.button("Go", key="summarise_document")


if st.session_state["summarise_document"] and uploaded_file is not None:
    if summarise_code:
        prompt = dedent("""
            Summarise this code as if you are writing documentation.

            First, describe the overall purpose of the code. 

            Next, highlight the key functions in the code and what they do.

            Finally, if there are public functions, give examples of how to use them.
            \n""")
    else:
        prompt = dedent("""
            Condense the content into a bullet point summary.

            Emphasise the main conclusion and its immediate importance.

            Use a maximum of ten bullet points.
            \n""")

    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
    string_data = stringio.read()
    user_query = {
        "role": "user",
        "content": prompt + string_data,
    }

    with chat_col:
        # Don't paste the whole document into the chat
        with st.chat_message("user"):
            summarisation_request = f"Requested summarisation of `{uploaded_file.name}` using the following prompt:\n\n {prompt}"
            st.markdown(summarisation_request)
            st.session_state["messages"].append(
                {"role": "user", "content": summarisation_request}
            )

        with st.chat_message("assistant"):

            def stream_summary_response(file_data):
                stream = ollama.chat(
                    model=st.session_state["model"],
                    messages=[user_query],
                    stream=True,
                )
                for chunk in stream:
                    yield chunk["message"]["content"]

            with st.spinner("Thinking...", show_time=False):
                message = st.write_stream(stream_summary_response(string_data))
            st.session_state["messages"].append(
                {"role": "assistant", "content": message}
            )


def handle_submit_prompt():
    # add latest message to history in format {role, content}
    prompt = st.session_state["user_prompt"]
    st.session_state["messages"].append({"role": "user", "content": prompt})
    st.session_state["generate_assistant"] = True


with chat_col:
    if st.session_state["generate_assistant"]:
        st.session_state["generate_assistant"] = False
        with st.chat_message("assistant"):
            with st.spinner("Thinking...", show_time=False):
                message = st.write_stream(stream_model_response())
            st.session_state["messages"].append(
                {"role": "assistant", "content": message}
            )
            # Right-align regenerate button
            left, right = st.columns([3, 1])
            with right:
                st.button(
                    "🔄 Regenerate", key="regenerate", on_click=regenerate_last_response
                )

st.chat_input("Enter prompt here...", key="user_prompt", on_submit=handle_submit_prompt)
