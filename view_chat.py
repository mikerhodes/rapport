from io import StringIO
from pathlib import Path
from typing import Dict, List, cast, Optional

import streamlit as st
from streamlit.elements.widgets.chat import ChatInputValue

from appconfig import ConfigStore
from chatgateway import ChatGateway, FinishReason
from chatmodel import (
    PAGE_HISTORY,
    AssistantMessage,
    Chat,
    IncludedFile,
    MessageList,
    SystemMessage,
    UserMessage,
    new_chat,
)
from chathistory import ChatHistoryManager


class State:
    chat: Chat
    user_prompt: ChatInputValue
    chat_gateway: ChatGateway
    model_context_length: int
    used_tokens: int
    generate_assistant: bool
    model: str
    history_manager: ChatHistoryManager
    finish_reason: FinishReason
    config_store: ConfigStore
    load_chat_with_id: Optional[str]


# _s acts as a typed accessor for session state.
_s = cast(State, st.session_state)


#
# Helpers
#


def clear_chat():
    """Clears the existing chat session"""
    del _s.chat
    # del st.session_state["chat"]


def _prepare_messages_for_model(
    messages: MessageList,
) -> List[Dict[str, str]]:
    """Converts message history format into format for model"""
    # Models like things in this order:
    # - System
    # - Files
    # - Chat
    # System and files for context, chat for the task
    result: List[Dict[str, str]] = []

    system = [m for m in messages if isinstance(m, SystemMessage)]
    file = [m for m in messages if isinstance(m, IncludedFile)]
    chat = [
        m
        for m in messages
        if isinstance(m, AssistantMessage) or isinstance(m, UserMessage)
    ]

    result.extend([{"role": m.role, "content": m.message} for m in system])
    for m in file:
        # Models don't have a file role, so convert
        prompt = f"""
        `{m.name}`
        ---
        {m.data}

        ---"""
        result.append({"role": m.role, "content": prompt})
    result.extend([{"role": m.role, "content": m.message} for m in chat])
    return result


def stream_model_response():
    """Returns a generator that yields chunks of the models respose"""
    # cg = cast(ChatGateway, st.session_state["chat_gateway"])
    response = _s.chat_gateway.chat(
        model=_s.chat.model,
        messages=_prepare_messages_for_model(_s.chat.messages),
        num_ctx=min(8192, st.session_state["model_context_length"]),
    )
    for chunk in (
        response
    ):  # prompt eval count is the token count used from the model
        if chunk.used_tokens is not None:
            _s.used_tokens = chunk.used_tokens
        if chunk.finish_reason is not None:
            _s.finish_reason = chunk.finish_reason
        yield chunk.content


def regenerate_last_response():
    """Regenerate the last assistant response"""
    # Remove the last assistant message
    _s.chat.messages = st.session_state["chat"].messages[:-1]
    _s.generate_assistant = True


def handle_submit_prompt():
    # add latest message to history in format {role, content}
    prompt = _s.user_prompt

    for f in prompt.files:
        data = StringIO(f.getvalue().decode("utf-8")).read()
        ext = f.name.split(".")[-1]
        _insert_file_chat_message(data, f.name, ext)

    if prompt.text.startswith("/include"):
        _handle_submit_include(prompt.text)
    else:
        _handle_submit_chat(prompt.text)

    save_current_chat()


def _handle_submit_chat(prompt: str):
    """Handle the user submitting a general chat prompt"""
    _s.chat.messages.append(UserMessage(message=prompt))
    _s.generate_assistant = True


def _handle_submit_include(prompt: str):
    """Handle the user trying to upload a file"""
    # Upload a file to the chat /attach /path/to/file
    parts = prompt.strip().split(" ")
    files = []
    if len(parts) == 2:
        files.append(Path(parts[1]))
    elif len(parts) == 3:  # path and glob
        files.extend(Path(parts[1]).glob(parts[2]))
    print(files)
    for p in files:
        try:
            _insert_file_chat_message(
                p.read_text(), p.name, p.suffix.lstrip(".")
            )
        except FileNotFoundError:
            print(f"Error: File '{p}' not found.")
            st.toast(f"Error: File '{p}' not found.")
        except PermissionError:
            print(f"Error: Permission denied for accessing the file '{p}'.")
            st.toast(
                f"Error: Permission denied for accessing the file '{p}'."
            )
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            st.toast(f"An unexpected error occurred uploading the file: {e}")


def _insert_file_chat_message(data, fname, fext: str):
    _s.chat.messages.append(IncludedFile(name=fname, ext=fext, data=data))


def handle_change_model():
    model = _s.model
    _s.chat.model = model
    _update_context_length(model)

    c = _s.config_store.load_config()
    c.last_used_model = model
    _s.config_store.save_config(c)


def _update_context_length(model):
    m = _s.chat_gateway.show(model)
    if m is not None:
        _s.model_context_length = m.context_length
    else:
        _s.model_context_length = 0


#
# Chat history
#


def generate_chat_title(chat: Chat) -> str:
    """Generate a title from the first few words of the first user message"""
    # Find first user message
    user_messages = [
        msg for msg in chat.messages if isinstance(msg, UserMessage)
    ]
    if not user_messages:
        return chat.title  # return existing title if can't do better

    # Take first 6 words of first message
    first_message = user_messages[0].message
    words = first_message.split()[:10]
    title = " ".join(words)

    # Add ellipsis if we truncated the message
    if len(words) < len(first_message.split()):
        title += "..."

    return title


def save_current_chat():
    """Save the current chat session"""
    if len(_s.chat.messages) > 1:  # More than just system message
        _s.chat.title = generate_chat_title(_s.chat)
        _s.history_manager.save_chat(_s.chat)


def load_chat(chat_id):
    """Load a chat from history"""
    chat = _s.history_manager.get_chat(chat_id)
    if chat:
        _s.chat = chat
        _s.model = chat.model
        handle_change_model()


def _chat_as_markdown() -> str:
    chat = _s.chat
    lines = []
    lines.append("---")
    lines.append("model: " + chat.model)
    lines.append("created_at: " + chat.created_at.isoformat())
    lines.append("---\n")
    lines.append(f"# {generate_chat_title(chat)}\n")
    for m in chat.messages:
        lines.append(f"**{m.role}**\n")
        if isinstance(m, IncludedFile):
            lines.append(
                f"""
File `{m.name}` included in conversation:

```{m.ext}
{m.data}
```
                """
            )
        else:
            lines.append(m.message)
        lines.append("\n")
    return "\n".join(lines)


#
# Initialise app state
#


# Don't generate a chat message until the user has prompted
if "generate_assistant" not in st.session_state:
    _s.generate_assistant = False

# Store the tokens used in the prompt
if "used_tokens" not in st.session_state:
    _s.used_tokens = 0

# Retrieve the current models from ollama
# Set a preferred model as default if there's none set
last_used_model = _s.config_store.load_config().last_used_model
models = _s.chat_gateway.list()
if "model" not in st.session_state:
    if last_used_model in models:
        _s.model = last_used_model
    else:
        _s.model = models[0]
_update_context_length(_s.model)

# Really need to figure something better for state defaults
if "load_chat_with_id" not in st.session_state:
    _s.load_chat_with_id = None
if chat_id := _s.load_chat_with_id:
    _s.load_chat_with_id = None
    load_chat(chat_id)

# Start a new chat if there isn't one active.
# "New Chat" is implemented as `del st.session_state["chat"]`
if "chat" not in st.session_state:
    _s.chat = new_chat(_s.model)
    _s.used_tokens = 0


#
# Start rendering the app
#


with st.sidebar:
    st.button(
        "New Chat",
        on_click=clear_chat,
        icon=":material/edit_square:",
        use_container_width=True,
    )
    st.download_button(
        "Download chat",
        _chat_as_markdown(),
        file_name="rapport_download.md",
        mime="text/markdown",
        use_container_width=True,
        icon=":material/download:",
        on_click="ignore",
    )
    st.selectbox(
        "Choose your model",
        models,
        key="model",
        on_change=handle_change_model,
    )

    # Display recent chats
    st.markdown("## Recent Chats")
    recent_chats = _s.history_manager.get_recent_chats(limit=3)

    for chat in recent_chats:
        # Highlight current chat
        icon = None
        if chat["id"] == _s.chat.id:
            icon = ":material/edit:"
        st.button(
            chat["title"],
            key=f"chat_{chat['id']}",
            on_click=load_chat,
            args=(chat["id"],),
            use_container_width=True,
            icon=icon,
        )

    st.page_link(PAGE_HISTORY, label="More chats ->")

chat_col, col2 = st.columns([3, 1])

with col2:
    st.markdown("""
        Slash commands:

        ```
        /include /path/to/file
        ```   

        Include a file's content into the chat.

        ```
        /include /path *.glob
        ```

        Include several files from path using pattern glob.
    """)

with chat_col:
    # Display chat messages from history on app rerun
    for message in _s.chat.messages:
        match message:
            case SystemMessage(message=message):
                with st.expander("View system prompt"):
                    st.markdown(message)
            case IncludedFile(name=name, ext=ext, data=data, role=role):
                with st.chat_message(role, avatar=":material/upload_file:"):
                    st.markdown(f"Included `{name}` in chat.")
                    with st.expander("View file content"):
                        st.markdown(f"```{ext}\n{data}\n```")
            case AssistantMessage() | UserMessage():
                with st.chat_message(message.role):
                    st.markdown(message.message)

    # Generate a reply and add to history
    if _s.generate_assistant:
        _s.generate_assistant = False

        # Using the .empty() container ensures that once the
        # model starts returning content, we replace the spinner
        # with the streamed content. We then also need to write
        # out the full message at the end (for some reason
        # the message otherwise disappears).
        with st.chat_message("assistant"), st.empty():
            with st.spinner("Thinking...", show_time=False):
                message = st.write_stream(stream_model_response())
            st.write(message)
            if isinstance(message, str):  # should always be
                _s.chat.messages.append(AssistantMessage(message=message))
            else:
                st.error(
                    "Could not add message to chat as unexpected return type"
                )
            save_current_chat()
            # st.rerun()

    # Allow user to regenerate the last response.
    if isinstance(_s.chat.messages[-1], AssistantMessage):
        left, right = st.columns([3, 1])
        with left:
            used_tokens_holder = st.empty()
            used_tokens_holder.caption(f"Used tokens: {_s.used_tokens}")
        with right:
            st.button(
                "Regenerate",
                key="regenerate",
                on_click=regenerate_last_response,
                type="tertiary",
                icon=":material/refresh:",
            )

try:
    if _s.finish_reason == FinishReason.Length:
        st.warning(
            "Model stopped because maximum tokens reached.",
            icon=":material/warning:",
        )
    del _s.finish_reason
except AttributeError:
    pass

st.chat_input(
    "Enter prompt here...",
    key="user_prompt",
    on_submit=handle_submit_prompt,
    accept_file=True,
)
