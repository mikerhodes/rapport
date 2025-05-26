import json
import logging
import shutil
import subprocess
import traceback
from io import StringIO
from pathlib import Path
from typing import Iterable, List, Optional, cast

import more_itertools
from pandas.core.base import textwrap
import streamlit as st
from pandas.core.frame import itertools
from streamlit.elements.widgets.chat import ChatInputValue

from rapport import appglobals, consts
from rapport.chatgateway import FinishReason
from rapport.chatmodel import (
    PAGE_HISTORY,
    AssistantMessage,
    Chat,
    IncludedFile,
    IncludedImage,
    ToolCallMessage,
    ToolResultMessage,
    UserMessage,
    new_chat,
)

logger = logging.getLogger(__name__)


class State:
    chat: Chat
    user_prompt: ChatInputValue
    generate_assistant: bool
    model: str
    models: List[str]
    finish_reason: FinishReason
    load_chat_with_id: Optional[str]


# _s acts as a typed accessor for session state.
_s = cast(State, st.session_state)


#
# Helpers
#


def _handle_new_chat():
    """Clears the existing chat session"""
    del _s.chat
    _s.chat = new_chat(_s.models, appglobals.configstore)
    _s.model = _s.chat.model


def stream_model_response(tool_acc: List[ToolCallMessage]):
    """Returns a generator that yields chunks of the models respose"""
    # cg = cast(ChatGateway, st.session_state["chat_gateway"])
    response = appglobals.chatgateway.chat(
        model=_s.chat.model,
        messages=_s.chat.messages,
        tools=appglobals.toolregistry.get_enabled_tools(),
    )

    # chunkier chunks so we don't force redraw too often, and we can
    # avoid ending chunks on escape characters like \ (to ensure that
    # things like latex \[ are complete in any chunk)
    chunkier_chunk = ""
    for chunk in response:
        if chunk.input_tokens is not None:
            _s.chat.input_tokens = chunk.input_tokens
        if chunk.output_tokens is not None:
            _s.chat.output_tokens = chunk.output_tokens
        if chunk.finish_reason is not None:
            _s.finish_reason = chunk.finish_reason
        if chunk.tool_call is not None:
            tool_acc.append(chunk.tool_call)

        # print(chunk.content)
        chunkier_chunk += chunk.content
        if not chunkier_chunk.endswith("\\") and len(chunkier_chunk) > 60:
            chunkier_chunk = post_process_chunk(chunkier_chunk)
            yield chunkier_chunk
            chunkier_chunk = ""

    yield chunkier_chunk  # don't forget the last chunk


def wait_n_and_chain(n, g_original) -> Iterable:
    # This allows us to wait for the first item in a "thinking" spinner
    # and then pass all the generated values to write_stream separately.
    # Get the first value
    g1 = []
    try:
        for _ in range(n):
            g1.append(next(g_original))
    except StopIteration:
        # Return what we have via chain
        pass

    return itertools.chain(g1, g_original)


def _handle_regenerate():
    """Regenerate the last assistant response"""
    # Remove the last assistant messages (can be >1 due to tool calls)
    i = 0
    for m in reversed(_s.chat.messages):
        match m.type:
            case (
                "AssistantMessage" | "ToolCallMessage" | "ToolResultMessage"
            ):
                i += 1
            case _:
                break
    _s.chat.messages = st.session_state["chat"].messages[:-i]
    _s.generate_assistant = True


def _handle_submit_prompt():
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
    fpath = appglobals.chatstore.import_image(_s.chat.id, fname, data)
    _s.chat.messages.append(IncludedImage(name=fname, path=fpath))


def _handle_change_model():
    model = _s.model
    _s.chat.model = model

    c = appglobals.configstore.load_config()
    c.last_used_model = model
    appglobals.configstore.save_config(c)


def post_process_chunk(s: str) -> str:
    s = openai_math_markup(s)
    return s


def openai_math_markup(s: str) -> str:
    """
    Support OpenAI latex markup (mostly equations) in
    return chunks by substituting the latex fences
    used in the OpenAI markdown with the fences used
    in streamlit.
    """
    # Support both inline and block markup. OpenAI uses
    # \[...equation perhaps surrounded by newline...\]
    # \(...equation perhaps surrounded by newline...\)
    #
    # Streamlit uses $ or $$. $$ works for both inline and
    # separate equation blocks, use that.
    return (
        s.replace(r"\[", "$$")
        .replace(r"\]", "$$")
        .replace(r"\(", "$$")
        .replace(r"\)", "$$")
    )


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

    # Take first line of user message
    first_message = user_messages[0].message
    title = first_message.split("\n")[0]

    return title


def save_current_chat():
    """Save the current chat session, writing to export file if set too."""
    if len(_s.chat.messages) > 1:  # More than just system message
        _s.chat.title = generate_chat_title(_s.chat)
        appglobals.chatstore.save_chat(_s.chat)
        if p := _s.chat.export_location:
            with open(p, "w") as f:
                f.write(_chat_as_markdown())


def _handle_load_chat(chat_id):
    """Load a chat from history"""
    chat = appglobals.chatstore.get_chat(chat_id)
    if chat:
        _s.chat = chat
        _s.model = chat.model
        _handle_change_model()


def _handle_obsidian_download():
    p = appglobals.configstore.load_config().obsidian_directory
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
        if m.type == "IncludedFile":
            lines.append(
                textwrap.dedent(f"""
                File `{m.name}` included in conversation:

                ```{m.ext}
                {m.data}
                ```
                """)
            )
        elif m.type == "IncludedImage":
            lines.append(
                textwrap.dedent(f"""
                Image `{m.name}` included in conversation.
                """)
            )
        elif m.type == "ToolCallMessage":
            lines.append(
                textwrap.dedent(f"""
                Tool Call: `{m.name}`

                ```json
                {json.dumps(m.parameters, indent=2)}
                ```
                """)
            )
        elif m.type == "ToolResultMessage":
            lines.append(
                textwrap.dedent(f"""
                Tool Result: `{m.name}`

                ```json
                {m.result}
                ```
                """)
            )
        else:
            lines.append(m.message)
        lines.append("\n")
    return "\n".join(lines)


#
# Initialise app state
#


def init_state():
    # Don't generate a chat message until the user has prompted
    if "generate_assistant" not in st.session_state:
        _s.generate_assistant = False

    _s.models = appglobals.chatgateway.list()
    if not _s.models:
        raise Exception(
            "No models available; run ollama or add Anthropic/watsonx credential environment variables."
        )

    # Really need to figure something better for state defaults
    if "load_chat_with_id" not in st.session_state:
        _s.load_chat_with_id = None
    if chat_id := _s.load_chat_with_id:
        _s.load_chat_with_id = None
        _handle_load_chat(chat_id)

    # Start a new chat if there isn't one active.
    # "New Chat" is implemented as `del st.session_state["chat"]`
    if "chat" not in st.session_state:
        _s.chat = new_chat(_s.models, appglobals.configstore)
    _s.model = _s.chat.model


#
# Start rendering the app
#


def render_sidebar():
    with st.sidebar:
        c1, c2 = st.columns([3, 1])
        with c1:
            st.button(
                "New Chat",
                on_click=_handle_new_chat,
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
                    appglobals.configstore.load_config().obsidian_directory
                    is not None
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
            _s.models,
            key="model",
            on_change=_handle_change_model,
        )

        # Display recent chats
        st.markdown("## Recent Chats")
        recent_chats = appglobals.chatstore.get_recent_chats(limit=2)

        for chat in recent_chats:
            # Highlight current chat
            icon = None
            if chat["id"] == _s.chat.id:
                icon = ":material/edit:"
            st.button(
                " ".join(chat["title"].split()[:6]) + "...",
                key=f"chat_{chat['id']}",
                on_click=_handle_load_chat,
                args=(chat["id"],),
                use_container_width=True,
                icon=icon,
            )

        st.page_link(PAGE_HISTORY, label="More chats ->")


def render_chat_messages():
    p = more_itertools.peekable(_s.chat.messages)
    for message in p:
        # Use the type discriminator field to determine the message type
        match message.type:
            case "SystemMessage":
                pass  # see view_config for display of system prompt
            case "UserMessage" | "IncludedFile" | "IncludedImage":
                _render_user_message_block(message, p)
            case "AssistantMessage" | "ToolCallMessage":
                _render_assistant_message_block(message, p)


def _render_user_message_block(
    first: UserMessage | IncludedFile | IncludedImage,
    p: more_itertools.peekable,
):
    """
    Renders a group of UserMessage, IncludedFile and IncludeImage
    messages into a single user chat block. Consumes the messages
    from `p`.
    """
    m = first
    with st.chat_message("user"):
        while True:
            match m.type:
                case "UserMessage":
                    st.markdown(m.message)
                case "IncludedFile":
                    with st.expander(f"Included `{m.name}` in chat."):
                        st.markdown(f"```{m.ext}\n{m.data}\n```")
                case "IncludedImage":
                    if appglobals.chatgateway.supports_images(_s.model):
                        _render_image_block(m, p)
                    else:
                        st.warning("Change model to use images.")
            # If no more items in iterable, or it's
            # not an assistant-type message, break
            if not p:
                break
            match p.peek().type:
                # We are still in the assistant's turn
                case "UserMessage" | "IncludedFile" | "IncludedImage":
                    m = next(p)
                    continue
                case _:
                    break


def _render_image_block(first: IncludedImage, p: more_itertools.peekable):
    """
    Render up to three images in columns, advancing the
    iterator.
    """
    cols = st.columns(4)
    maybe_img = first
    col_idx = 0
    while maybe_img.type == "IncludedImage" and col_idx < len(cols):
        with cols[col_idx]:
            st.image(str(maybe_img.path))
        if not p:
            return
        maybe_img = next(p)
        if not maybe_img.type == "IncludedImage":
            p.prepend(maybe_img)  # put it back and return
            return
        col_idx += 1


def _render_assistant_message_block(
    first: AssistantMessage | ToolCallMessage,
    p: more_itertools.peekable,
):
    """
    Renders a group of AssistantMessage and tool call messages
    into a single assistant chat block. Consumes the messages
    from `p`.
    """
    # Render tool calls inline if we find them following this
    # message. We peek the iterator in the while loop, advancing
    # it if we find tool calls to render.
    # This displays tool calls nicely inline with the model text
    # referencing them.
    m = first
    with st.chat_message("assistant"):
        while True:
            match m.type:
                case "AssistantMessage":
                    st.markdown(m.message)
                case "ToolCallMessage":
                    _render_tool_call(m, next(p))
            # If no more items in iterable, or it's
            # not an assistant-type message, break
            if not p:
                break
            match p.peek().type:
                # We are still in the assistant's turn
                case "AssistantMessage" | "ToolCallMessage":
                    m = next(p)
                    continue
                case _:
                    break


def _render_tool_call(tool_call, tool_response):
    with st.expander(f"**Tool Call: {tool_call.name}**"):
        st.caption("Parameters")
        st.code(tool_call.parameters)
        if tool_response is not None:
            st.caption("Result")
            # Show a maximum of about 16 lines
            # There are about 16 lines rendered into 400 height,
            # padding is 30px, so 24px per line with a min height
            # of 1 line is 54.
            c = len(tool_response.result.splitlines())
            h = max(54, int(min(c * 24, 400)))
            st.code(tool_response.result, height=h)


def generate_assistant_message():
    with st.chat_message("assistant"):
        turns = 20  # limit tool-calling turns for safety
        while turns:
            turns -= 1

            tool_acc: List[ToolCallMessage] = []

            try:
                with st.spinner("Thinking...", show_time=False):
                    g = wait_n_and_chain(2, stream_model_response(tool_acc))
                m = st.write_stream(g)

                # should be str, might be empty if model immediately
                # does a tool call.
                if isinstance(m, str):
                    if m:  # only add if model sent text content
                        _s.chat.messages.append(AssistantMessage(message=m))
                else:
                    logger.error("Bad chat return type; not added to chat.")

            except Exception as e:
                print(e)
                print(traceback.format_exc())
                print("Error calling remote model")
                st.error(e)

            tool_use = len(tool_acc) > 0

            for tool_call in tool_acc:
                try:
                    result = ToolResultMessage(
                        id=tool_call.id,
                        name=tool_call.name,
                        result=appglobals.toolregistry.execute_tool(
                            tool_call.name,
                            tool_call.parameters,
                        ),
                    )
                    _s.chat.messages.extend([tool_call, result])
                    _render_tool_call(tool_call, result)
                except ValueError as ex:
                    logger.error("Error running tool:", ex)

            save_current_chat()

            # If we have tool use, go around again
            if tool_use:
                continue
            else:
                break


def render_assistant_message_footer():
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
            on_click=_handle_regenerate,
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


def render_chat_input():
    st.chat_input(
        "Your message",
        key="user_prompt",
        on_submit=_handle_submit_prompt,
        accept_file="multiple",
        file_type=consts.TEXT_FILE_EXTENSIONS + consts.IMAGE_FILE_EXTENSIONS,
    )


def main():
    try:
        init_state()
        render_sidebar()
        render_chat_messages()
        if _s.generate_assistant:
            _s.generate_assistant = False
            generate_assistant_message()
        if isinstance(_s.chat.messages[-1], AssistantMessage):
            render_assistant_message_footer()
        render_chat_input()
    except Exception as e:
        print(e)
        print(traceback.format_exc())
        st.error(e, icon=":material/error:")


if __name__ == "__main__":
    main()
