import logging
import os
from enum import Enum
from pathlib import Path
from typing import (
    Generator,
    List,
    Tuple,
)

from anthropic import Anthropic
from anthropic.types import (
    Base64ImageSourceParam,
    CacheControlEphemeralParam,
    DocumentBlockParam,
    ImageBlockParam,
    MessageParam,
    PlainTextSourceParam,
    TextBlockParam,
    ToolResultBlockParam,
    ToolUseBlockParam,
)

from rapport.chatmodel import (
    MessageList,
    SystemMessage,
    ToolCallMessage,
)
from rapport.tools import Tool

from .types import (
    BadImageFormat,
    ChatAdaptor,
    FinishReason,
    MessageChunk,
    MissingEnvVarException,
)

logger = logging.getLogger(__name__)


class AnthropicAdaptor(ChatAdaptor):
    models: List[str]
    c: Anthropic

    def _prepare_messages_for_model(
        self,
        messages: MessageList,
    ) -> Tuple[List[TextBlockParam], List[MessageParam]]:
        """
        Return (system_prompt, message_list) in Anthropic client
        format.
        The Anthropic SDK expects the system prompt in a separate
        argument, so return it separately.
        In addition, return messages in the order they appear in
        the chat.
        """

        sys_str = "\n\n".join(
            [m.message for m in messages if isinstance(m, SystemMessage)]
        )
        system_prompt = [TextBlockParam(text=sys_str, type="text")]

        output = []

        for m in messages:
            mp = None
            match m.type:
                case "UserMessage":
                    mp = MessageParam(
                        role="user",
                        content=[
                            TextBlockParam(
                                type="text",
                                text=m.message,
                            )
                        ],
                    )
                case "AssistantMessage" if m.message:
                    mp = MessageParam(
                        role="assistant",
                        content=[
                            TextBlockParam(
                                type="text",
                                text=m.message,
                            )
                        ],
                    )
                case "IncludedFile":
                    p = self._prepare_documentblockparam(m.data)
                    mp = MessageParam(
                        role="user",
                        content=[p],
                    )
                case "IncludedImage":
                    p = self._prepare_imageblockparam(m.path)
                    mp = MessageParam(
                        role="user",
                        content=[p],
                    )
                case "ToolCallMessage":
                    mp = MessageParam(
                        role="assistant",
                        content=[
                            ToolUseBlockParam(
                                type="tool_use",
                                id=m.id,
                                input=m.parameters,
                                name=m.name,
                            )
                        ],
                    )
                case "ToolResultMessage":
                    mp = MessageParam(
                        role="user",
                        content=[
                            ToolResultBlockParam(
                                tool_use_id=m.id,
                                type="tool_result",
                                content=m.result,
                            )
                        ],
                    )
                case _:
                    pass
            if mp:
                output.append(mp)

        # If last message is user, apply prompt caching
        match output[-1]:
            case {"role": "user", "content": [c]}:
                print("applying prompt caching")
                c["cache_control"] = CacheControlEphemeralParam(
                    type="ephemeral"
                )
                output[-1] = MessageParam(role="user", content=[c])

        return (system_prompt, output)

    def _prepare_documentblockparam(self, text: str) -> DocumentBlockParam:
        return DocumentBlockParam(
            type="document",
            source=PlainTextSourceParam(
                type="text",
                media_type="text/plain",
                data=text,
            ),
        )

    def _prepare_imageblockparam(self, image_path: Path) -> ImageBlockParam:
        """Convert image to base64 for Anthropic API"""
        import base64

        with open(image_path, "rb") as img_file:
            base64_image = base64.b64encode(img_file.read()).decode("utf-8")

        match image_path.suffix.lower():
            case ".png":
                mime_type = "image/png"
            case ".gif":
                mime_type = "image/gif"
            case ".webp":
                mime_type = "image/webp"
            case ".jpg" | ".jpeg":
                mime_type = "image/jpeg"
            case other:
                raise BadImageFormat(other)

        return ImageBlockParam(
            type="image",
            source=Base64ImageSourceParam(
                type="base64", media_type=mime_type, data=base64_image
            ),
        )

    def __init__(self):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise MissingEnvVarException("ANTHROPIC_API_KEY")

        # For now we hardcode Claude models we want to use
        # while we firm up how ChatGateway should work.
        self.models = [
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-latest",
            "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest",
        ]
        self.c = Anthropic()

    def list(self) -> List[str]:
        return self.models

    def supports_images(self, model: str) -> bool:
        # All the Anthropic models we provide support images
        return True

    def chat(
        self,
        model: str,
        messages: MessageList,
        tools: List[Tool],
    ) -> Generator[MessageChunk, None, None]:
        system_prompt, anth_messages = self._prepare_messages_for_model(
            messages
        )

        anth_tools = [x.render_anthropic() for x in tools]

        chunk_stream = None
        try:
            chunk_stream = self.c.messages.create(
                max_tokens=8192,
                messages=anth_messages,
                model=model,
                stream=True,
                system=system_prompt,
                tools=anth_tools,
            )
            input_tokens = 0
        except Exception as ex:
            print(messages)
            print("=" * 20)
            print(anth_messages)
            print(ex)

        if chunk_stream is None:
            return

        import json

        class StreamState(Enum):
            START = 1
            TEXT = 2
            TOOL = 3

        state = StreamState.START
        tool_call_id = ""
        tool_call_name = ""
        tool_call_input = ""

        for event in chunk_stream:
            # logger.info(event.type)
            content = ""
            finish_reason = None
            input_tokens = None
            output_tokens = None

            match state:
                case StreamState.START:
                    match event.type:
                        case "message_start":
                            input_tokens = event.message.usage.input_tokens
                        case "content_block_start" if (
                            event.content_block.type == "text"
                        ):
                            # new text content
                            state = StreamState.TEXT
                        case "content_block_start" if (
                            event.content_block.type == "tool_use"
                        ):
                            # new tool call
                            state = StreamState.TOOL
                            tool_call_id = event.content_block.id
                            tool_call_name = event.content_block.name
                            tool_call_input = ""
                        case "message_delta":
                            output_tokens = event.usage.output_tokens
                            match event.delta.stop_reason:
                                case "max_tokens":
                                    finish_reason = FinishReason.Length
                                case _:
                                    finish_reason = FinishReason.Stop
                        case "message_stop":
                            pass  # should be the last message
                        case _:
                            print(event)
                    yield MessageChunk(
                        content="",
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        finish_reason=finish_reason,
                        tool_call=None,
                    )
                case StreamState.TEXT:
                    match event.type:
                        case "content_block_delta" if (
                            event.delta.type == "text_delta"
                        ):
                            content = event.delta.text
                            yield MessageChunk(
                                content=content,
                                input_tokens=None,
                                output_tokens=None,
                                finish_reason=None,
                                tool_call=None,
                            )
                        case "content_block_stop":
                            state = StreamState.START
                        case _:
                            print(event)
                case StreamState.TOOL:
                    match event.type:
                        case "content_block_delta" if (
                            event.delta.type == "input_json_delta"
                        ):
                            tool_call_input += event.delta.partial_json
                        case "content_block_stop":
                            print(
                                "tool_call:",
                                tool_call_id,
                                tool_call_name,
                                tool_call_input,
                            )
                            yield MessageChunk(
                                content="",
                                input_tokens=None,
                                output_tokens=None,
                                finish_reason=None,
                                tool_call=ToolCallMessage(
                                    id=tool_call_id,
                                    name=tool_call_name,
                                    parameters=json.loads(tool_call_input),
                                ),
                            )
                            # yield tool use
                            state = StreamState.START
                        case _:
                            print(event)
