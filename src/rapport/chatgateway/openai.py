import logging
import os
from pathlib import Path
from typing import (
    Generator,
    Iterable,
    List,
    cast,
)

import openai
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionChunk,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from rapport.chatmodel import (
    MessageList,
    SystemMessage,
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


class OpenAIAdaptor(ChatAdaptor):
    models: List[str]
    c: openai.Client

    def __init__(self):
        self.models = []

        if not os.environ.get("OPENAI_API_KEY"):
            raise MissingEnvVarException("OPENAI_API_KEY")

        self.c = openai.Client(api_key=os.environ["OPENAI_API_KEY"])
        self.models.extend(
            [
                "gpt-4.1",
                "gpt-4.1-mini",
                "gpt-4.1-nano",
                "gpt-4o-mini",
                "gpt-4o",
            ]
        )

    def list(self) -> List[str]:
        return self.models

    def supports_images(self, model: str) -> bool:
        return True

    def chat(
        self,
        model: str,
        messages: MessageList,
        tools: List[Tool],
    ) -> Generator[MessageChunk, None, None]:
        # cast until we make an openai specific message prep function
        messages_content = self._prepare_messages_for_model(messages)
        completion = self.c.chat.completions.create(
            model=model,
            store=False,
            stream=True,
            max_tokens=8192,
            messages=messages_content,
        )

        for event in completion:
            event = cast(ChatCompletionChunk, event)
            finish_reason = None
            content = "".join(
                [x.delta.content for x in event.choices if x.delta.content]
            )
            match event.choices[0].finish_reason:
                case "stop":
                    finish_reason = FinishReason.Stop
                case "length":
                    finish_reason = FinishReason.Length
                case None:
                    finish_reason = None
                case _:
                    finish_reason = FinishReason.Other

            yield MessageChunk(
                content=content,
                input_tokens=None,
                output_tokens=None,
                finish_reason=finish_reason,
                tool_call=None,
            )

    def _prepare_messages_for_model(
        self,
        messages: MessageList,
    ) -> Iterable[ChatCompletionMessageParam]:
        """
        Converts message history format into format for model.

        This implementation only supports "basic" message types,
        specifically ones that can be rendered to text. ChatAdaptors
        that support more advanced models will need to add their
        own implementations (see AnthropicAdaptor for an example).
        """
        # Models like things in this order:
        # - System
        # - Files
        # - Chat
        # System and files for context, chat for the task
        result: Iterable[ChatCompletionMessageParam] = []

        system_prompt = "\n\n".join(
            [m.message for m in messages if isinstance(m, SystemMessage)]
        )
        result.append(
            ChatCompletionSystemMessageParam(
                role="system", content=system_prompt
            )
        )

        remaining = [m for m in messages if not isinstance(m, SystemMessage)]
        for m in remaining:
            match m.type:
                case "UserMessage":
                    x = ChatCompletionUserMessageParam(
                        role="user", content=m.message
                    )
                    result.append(x)
                case "AssistantMessage":
                    x = ChatCompletionAssistantMessageParam(
                        role="assistant", content=m.message
                    )
                    result.append(x)
                case "IncludedFile":
                    # This format seems to work well for models without
                    # a specific document type in their API.
                    prompt = f"""
                    `{m.name}`
                    ---
                    {m.data}

                    ---"""
                    x = ChatCompletionUserMessageParam(
                        role="user", content=prompt
                    )
                    result.append(x)
                case "IncludedImage":
                    result.append(self._prepare_imageblockparam(m.path))

        return result

    def _prepare_imageblockparam(
        self, image_path: Path
    ) -> ChatCompletionUserMessageParam:
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

        return {
            "role": "user",
            "content": [
                {
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_image}",
                    },
                    "type": "image_url",
                }
            ],
        }
