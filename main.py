from io import StringIO
from pathlib import Path

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

# Store the tokens used in the prompt
if "used_tokens" not in st.session_state:
    st.session_state["used_tokens"] = 0

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
    st.session_state["used_tokens"] = 0


def stream_model_response():
    """Returns a generator that yields chunks of the models respose"""
    m = ollama.show(st.session_state["model"])
    model_context_length = m.modelinfo[f"{m.details.family}.context_length"]
    print(m.details.family, model_context_length)
    response = ollama.chat(
        model=st.session_state["model"],
        messages=st.session_state["messages"],
        stream=True,
        options=ollama.Options(
            num_ctx=min(8192, model_context_length),
        ),
    )
    for chunk in response:  # prompt eval count is the token count used from the model
        if chunk.prompt_eval_count is not None:
            st.session_state["used_tokens"] = chunk.prompt_eval_count + chunk.eval_count
        yield chunk["message"]["content"]


def regenerate_last_response():
    """Regenerate the last assistant response"""
    # Remove the last assistant message
    st.session_state["messages"] = st.session_state["messages"][:-1]
    st.session_state["generate_assistant"] = True


def handle_submit_prompt():
    # add latest message to history in format {role, content}
    prompt = st.session_state["user_prompt"]
    if prompt.startswith("/include"):
        _handle_submit_include(prompt)
    else:
        _handle_submit_chat(prompt)


def _handle_submit_chat(prompt: str):
    """Handle the user submitting a general chat prompt"""
    st.session_state["messages"].append({"role": "user", "content": prompt})
    st.session_state["generate_assistant"] = True


def _handle_submit_include(prompt: str):
    """Handle the user trying to upload a file"""
    # Upload a file to the chat /attach /path/to/file
    p = Path(prompt.strip().removeprefix("/include "))
    try:
        string_data = p.read_text()
        ext = p.suffix.lstrip(".")
        _insert_file_chat_message(string_data, p.name, ext)
    except FileNotFoundError:
        print(f"Error: File '{p}' not found.")
        st.toast(f"Error: File '{p}' not found.")
    except PermissionError:
        print(f"Error: Permission denied for accessing the file '{p}'.")
        st.toast(f"Error: Permission denied for accessing the file '{p}'.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        st.toast(f"An unexpected error occurred uploading the file: {e}")


def handle_add_doc_to_chat():
    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
    string_data = stringio.read()
    ext = uploaded_file.name.split(".")[-1]
    _insert_file_chat_message(string_data, uploaded_file.name, ext)


def _insert_file_chat_message(data, fname, fext: str):
    prompt = f"Including content of file `{fname}` below:\n\n```{fext}\n{data}\n```"
    st.session_state["messages"].append(
        {
            "role": "user",
            "content": prompt,
        }
    )


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
                title,
                key=f"chat_{chat['id']}",
                on_click=load_chat,
                args=[chat["id"]],
                use_container_width=True,
            )
        with col2:
            st.button(
                "🗑️", key=f"delete_{chat['id']}", on_click=delete_chat, args=[chat["id"]]
            )

chat_col, col2 = st.columns([3, 1])

with col2:
    with st.expander("Upload a file"):
        uploaded_file = st.file_uploader("Upload a plain text, markdown or code file")
        st.button("Add to Chat", on_click=handle_add_doc_to_chat)
    st.markdown("""
        Slash commands:

        ```
        /include /path/to/file
        ```   

        Include a file's content into the chat.
    """)

with chat_col:
    # Display chat messages from history on app rerun
    for message in st.session_state["messages"]:
        if message["role"] == "system":
            with st.expander("View system prompt"):
                st.markdown(message["content"])
        elif message["content"].startswith("Including content of file `"):
            with st.chat_message(message["role"]):
                before, _, after = message["content"].partition("\n")
                st.markdown(before)
                with st.expander("View file content"):
                    st.markdown(after)
        else:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # Generate a reply and add to history
    if st.session_state["generate_assistant"]:
        st.session_state["generate_assistant"] = False
        with st.chat_message("assistant"):
            with st.spinner("Thinking...", show_time=False):
                message = st.write_stream(stream_model_response())
            st.session_state["messages"].append(
                {"role": "assistant", "content": message}
            )

    # Allow user to regenerate the last response.
    if st.session_state["messages"][-1]["role"] == "assistant":
        left, right = st.columns([3, 1])
        with left:
            used_tokens_holder = st.empty()
            used_tokens_holder.caption(
                f"Used tokens: {st.session_state['used_tokens']}"
            )
        with right:
            st.button(
                "🔄 Regenerate",
                key="regenerate",
                on_click=regenerate_last_response,
                type="tertiary",
            )

st.chat_input("Enter prompt here...", key="user_prompt", on_submit=handle_submit_prompt)

# Update the used tokens with the latest value after
# generating a new response.
used_tokens_holder.caption(f"Used tokens: {st.session_state['used_tokens']}")
