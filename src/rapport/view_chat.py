from io import StringIO
import io
import logging
import traceback
from pathlib import Path
import shutil
import subprocess
from typing import cast, Optional

from PIL import Image
from PIL.Image import Resampling
import streamlit as st
from streamlit.elements.widgets.chat import ChatInputValue

from rapport import consts
from rapport.appconfig import ConfigStore
from rapport.chatgateway import ChatGateway, FinishReason
from rapport.chatmodel import (
    PAGE_HISTORY,
    AssistantMessage,
    Chat,
    IncludedFile,
    IncludedImage,
    SystemMessage,
    UserMessage,
    new_chat,
)
from rapport.chathistory import ChatHistoryManager

logger = logging.getLogger(__name__)


class State:
    chat: Chat
    user_prompt: ChatInputValue
    chat_gateway: ChatGateway
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


def stream_model_response():
    """Returns a generator that yields chunks of the models respose"""
    # cg = cast(ChatGateway, st.session_state["chat_gateway"])
    response = _s.chat_gateway.chat(
        model=_s.chat.model,
        messages=_s.chat.messages,
    )
    for chunk in (
        response
    ):  # prompt eval count is the token count used from the model
        if chunk.input_tokens is not None:
            _s.chat.input_tokens = chunk.input_tokens
        if chunk.output_tokens is not None:
            _s.chat.output_tokens = chunk.output_tokens
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
        file_ext = Path(f.name).suffix.lower()
        if file_ext in consts.IMAGE_FILE_EXTENSIONS:
            _insert_image_chat_message(f.getvalue(), f.name)
        else:
            data = StringIO(f.getvalue().decode("utf-8")).read()
            ext = f.name.split(".")[-1]
            _insert_file_chat_message(data, f.name, ext)

    # if the user just uploaded some files to the chat,
    # don't invoke the model.
    if not prompt.text:
        return

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


def _insert_image_chat_message(data: bytes, fname: str):
    # Claude recommends image sizes of 1,500px or less on the longest
    # side. So let's resize the image to be smaller than that.
    im = Image.open(io.BytesIO(data))
    fmt = im.format
    orig_width, orig_height = im.size
    im.thumbnail((1200, 1200), Resampling.LANCZOS)
    width, height = im.size
    print(f"Resized image: {orig_width}x{orig_height} -> {width}x{height}")
    data_resized = io.BytesIO()
    im.save(data_resized, format=fmt)

    # Save image to chat store
    dir = Path.home() / ".config" / "rapport" / "temp_images"
    dir.mkdir(exist_ok=True, parents=True)
    fpath = dir / f"{_s.chat.id}-{fname}"
    with open(fpath, "wb") as img_file:
        img_file.write(data_resized.getvalue())
    _s.chat.messages.append(IncludedImage(name=fname, path=fpath))


def handle_change_model():
    model = _s.model
    _s.chat.model = model

    c = _s.config_store.load_config()
    c.last_used_model = model
    _s.config_store.save_config(c)


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
    """Save the current chat session, writing to export file if set too."""
    if len(_s.chat.messages) > 1:  # More than just system message
        _s.chat.title = generate_chat_title(_s.chat)
        _s.history_manager.save_chat(_s.chat)
        if p := _s.chat.export_location:
            with open(p, "w") as f:
                f.write(_chat_as_markdown())


def load_chat(chat_id):
    """Load a chat from history"""
    chat = _s.history_manager.get_chat(chat_id)
    if chat:
        _s.chat = chat
        _s.model = chat.model
        handle_change_model()


def _handle_obsidian_download():
    p = _s.config_store.load_config().obsidian_directory
    if p:
        p = Path(p) / f"{_s.chat.title}-{_s.chat.id}.md"
        _s.chat.export_location = p
        save_current_chat()  # this also writes the obsidian file
        st.toast("Saved to Obsidian")

    else:
        st.toast("Path not set")


def _handle_copy_to_clipboard():
    """Use pbcopy to copy to clipboard"""
    # TODO support other OSs.
    try:
        p = subprocess.run(
            ["pbcopy", "w"],
            input=_chat_as_markdown().encode("utf-8"),
        )
        if p.returncode == 0:
            st.toast("Copied to clipboard")
        else:
            st.toast(f"pbcopy execute failed: exited with {p.returncode}")
    except Exception as ex:
        logger.error("Exception executing pbcopy tool: %s", ex)
        st.toast("Error executing pbcopy tool; check logs.")


def _handle_create_gist():
    """Create a gist using the gh tool"""
    try:
        p = subprocess.run(
            [
                "gh",
                "gist",
                "create",
                "-f",
                f"{_s.chat.title}-{_s.chat.id}.md",
                "-d",
                generate_chat_title(_s.chat),
                "-",
            ],
            input=_chat_as_markdown().encode("utf-8"),
        )
        if p.returncode == 0:
            st.toast("Saved as gist")
        else:
            st.toast(f"gh execute failed: exited with {p.returncode}")
    except Exception as ex:
        logger.error("Exception executing gh tool: %s", ex)
        st.toast("Error executing gh tool; check logs.")


def _chat_as_markdown() -> str:
    chat = _s.chat
    lines = []
    lines.append("---")
    lines.append("model: " + chat.model)
    lines.append("created_at: " + chat.created_at.isoformat())
    lines.append("updated_at: " + chat.updated_at.isoformat())
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
        elif isinstance(m, IncludedImage):
            lines.append(
                f"""
Image `{m.name}` included in conversation.
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

# Retrieve the current models from ollama
# Set a preferred model as default if there's none set
last_used_model = _s.config_store.load_config().last_used_model
models = _s.chat_gateway.list()
if "model" not in st.session_state:
    if last_used_model in models:
        _s.model = last_used_model
    else:
        _s.model = models[0]

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


#
# Start rendering the app
#


with st.sidebar:
    c1, c2 = st.columns([3, 1])
    with c1:
        st.button(
            "New Chat",
            on_click=clear_chat,
            icon=":material/edit_square:",
            use_container_width=True,
        )
    with c2:
        with st.popover(
            "",
            icon=":material/export_notes:",
            disabled=len(_s.chat.messages) < 2,
        ):
            st.download_button(
                "Download",
                _chat_as_markdown(),
                file_name="rapport_download.md",
                mime="text/markdown",
                use_container_width=True,
                icon=":material/download:",
                on_click="ignore",
            )
            st.button(
                "Copy to clipboard",
                on_click=_handle_copy_to_clipboard,
                icon=":material/content_copy:",
                use_container_width=True,
            )
            obsidian_av = (
                _s.config_store.load_config().obsidian_directory is not None
            )
            st.button(
                "Obsidian"
                if obsidian_av
                else "Set Obsidian directory to save to Obsidian",
                on_click=_handle_obsidian_download,
                icon=":material/check:"
                if _s.chat.export_location
                else ":material/add_circle:",
                use_container_width=True,
                disabled=not obsidian_av,
            )
            gh_tool_available = shutil.which("gh") is not None
            st.button(
                "Upload as gist"
                if gh_tool_available
                else "Install gh tool to enable gist upload",
                on_click=_handle_create_gist,
                icon=":material/cloud_upload:",
                use_container_width=True,
                disabled=not gh_tool_available,
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
            case IncludedImage(name=name, path=path, role=role):
                with st.chat_message(role, avatar=":material/image:"):
                    st.markdown(f"Included image `{name}` in chat.")
                    if _s.chat_gateway.supports_images(_s.model):
                        st.image(str(path))
                    else:
                        st.warning("Change model to use images.")
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
            try:
                with st.spinner("Thinking...", show_time=False):
                    message = st.write_stream(stream_model_response())
                st.write(message)
                if isinstance(message, str):  # should always be
                    _s.chat.messages.append(
                        AssistantMessage(message=message)
                    )
                else:
                    st.error(
                        "Could not add message to chat as unexpected return type"
                    )
                save_current_chat()
                # st.rerun()
            except Exception as e:
                print(e)
                print(traceback.format_exc())
                print("The server could not be reached")
                st.error(e)

    # Allow user to regenerate the last response.
    if isinstance(_s.chat.messages[-1], AssistantMessage):
        left, right = st.columns([3, 1])
        with left:
            used_tokens_holder = st.empty()
            used_tokens_holder.caption(
                "Used tokens: input {} / output: {}".format(
                    _s.chat.input_tokens,
                    _s.chat.output_tokens,
                )
            )
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
    "Your message",
    key="user_prompt",
    on_submit=handle_submit_prompt,
    accept_file="multiple",
    file_type=consts.TEXT_FILE_EXTENSIONS + consts.IMAGE_FILE_EXTENSIONS,
)
