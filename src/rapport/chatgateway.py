import logging
import os
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import (
    Dict,
    Generator,
    List,
    Optional,
    Protocol,
    Tuple,
    cast,
    Iterable,
)

import ibm_watsonx_ai as wai
import ibm_watsonx_ai.foundation_models as waifm
import openai
import ollama
from anthropic import Anthropic
from anthropic.types import (
    Base64ImageSourceParam,
    CacheControlEphemeralParam,
    DocumentBlockParam,
    ImageBlockParam,
    MessageParam,
    PlainTextSourceParam,
    TextBlockParam,
)
from ibm_watsonx_ai.wml_client_error import WMLClientError
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionChunk,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from rapport.chatmodel import (
    AssistantMessage,
    IncludedFile,
    IncludedImage,
    MessageList,
    SystemMessage,
    UserMessage,
)

logger = logging.getLogger(__name__)


class FinishReason(Enum):
    Stop = auto()
    Length = auto()
    Other = auto()


@dataclass
class ModelInfo:
    name: str
    context_length: int


@dataclass
class MessageChunk:
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    content: str
    finish_reason: Optional[FinishReason]


class ChatAdaptor(Protocol):
    """ChatAdaptor adapts an LLM interface to ChatGateway's expectations."""

    def list(self) -> List[str]: ...

    def supports_images(self, model: str) -> bool: ...

    def chat(
        self,
        model: str,
        messages: MessageList,
    ) -> Generator[MessageChunk, None, None]: ...


class MissingEnvVarException(Exception):
    def __str__(self) -> str:
        return f"Missing env var: {self.args[0]}"


class BadImageFormat(Exception):
    def __str__(self) -> str:
        return f"Unsupported image format: {self.args[0]}"


class ChatException(Exception):
    def __str__(self) -> str:
        return self.args[0]


class ChatGateway:
    models: List[str]
    model_to_client: Dict[str, ChatAdaptor]

    def __init__(self):
        """Load up the available models"""
        self.models = []
        self.model_to_client = {}

        try:
            oa = OllamaAdaptor()
            self.models.extend(oa.list())
            for m in oa.list():
                self.model_to_client[m] = oa
        except ConnectionError:
            logger.info("Ollama not running; cannot use ollama models")

        try:
            aa = AnthropicAdaptor()
            self.models.extend(aa.list())
            for m in aa.list():
                self.model_to_client[m] = aa
        except MissingEnvVarException as ex:
            logger.info(f"Warning: {ex}; cannot use Anthropic models")

        try:
            wa = WatsonxAdaptor()
            self.models.extend(wa.list())
            for m in wa.list():
                self.model_to_client[m] = wa
        except MissingEnvVarException as ex:
            logger.info(f"Warning: {ex}; cannot use watsonx models")

        try:
            oa = OpenAIAdaptor()
            self.models.extend(oa.list())
            for m in oa.list():
                self.model_to_client[m] = oa
        except MissingEnvVarException as ex:
            logger.info(f"Warning: {ex}; cannot use OpenAI models")

    def list(self) -> List[str]:
        return self.models

    def supports_images(self, model: str) -> bool:
        """Check if the model supports image inputs"""
        c = self.model_to_client[model]
        return c.supports_images(model)

    def chat(
        self,
        model: str,
        messages: MessageList,
    ) -> Generator[MessageChunk, None, None]:
        c = self.model_to_client[model]
        response = c.chat(
            model=model,
            messages=messages,
        )
        for chunk in response:
            yield chunk


def _prepare_messages_for_model(
    messages: MessageList,
) -> List[Dict[str, str]]:
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
        # This format seems to work well for models without
        # a specific document type in their API.
        prompt = f"""
        `{m.name}`
        ---
        {m.data}

        ---"""
        result.append({"role": m.role, "content": prompt})
    result.extend([{"role": m.role, "content": m.message} for m in chat])
    return result


class OllamaAdaptor(ChatAdaptor):
    models: List[str]
    c: ollama.Client

    def __init__(self):
        self.models = []

        self.c = ollama.Client()
        ollama_models = [model["model"] for model in self.c.list()["models"]]
        self.models.extend(ollama_models)

    def list(self) -> List[str]:
        return self.models

    def supports_images(self, model: str) -> bool:
        return False

    def _show(self, model: str) -> Optional[ModelInfo]:
        m = self.c.show(model)
        if m and m.modelinfo and m.details:
            return ModelInfo(
                model, m.modelinfo[f"{m.details.family}.context_length"]
            )
        else:
            return None

    def chat(
        self,
        model: str,
        messages: MessageList,
    ) -> Generator[MessageChunk, None, None]:
        messages_content = _prepare_messages_for_model(messages)
        m = self._show(model)
        if m is None:
            logger.error("Ollama chat got unknown model: %s", model)
            return
        # Truncate the context length to reduce memory usage
        # TODO make this an option?
        num_ctx = min(8192, m.context_length)

        response = self.c.chat(
            model=model,
            messages=messages_content,
            stream=True,
            options=ollama.Options(
                num_ctx=num_ctx,
            ),
        )
        for chunk in response:
            finish_reason = None
            input_tokens = None
            output_tokens = None
            if chunk.get("done", False):
                finish_reason = FinishReason.Stop
            if chunk.prompt_eval_count and chunk.eval_count:
                input_tokens = chunk.prompt_eval_count
                output_tokens = chunk.eval_count
            yield MessageChunk(
                content=chunk["message"]["content"],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                finish_reason=finish_reason,
            )


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
            match m:
                case UserMessage():
                    x = ChatCompletionUserMessageParam(
                        role="user", content=m.message
                    )
                    result.append(x)
                case AssistantMessage():
                    x = ChatCompletionAssistantMessageParam(
                        role="assistant", content=m.message
                    )
                    result.append(x)
                case IncludedFile():
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
                case IncludedImage():
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
            match m:
                case UserMessage():
                    mp = MessageParam(
                        role="user",
                        content=m.message,
                    )
                case AssistantMessage():
                    mp = MessageParam(
                        role="assistant",
                        content=m.message,
                    )
                case IncludedFile():
                    p = self._prepare_documentblockparam(m.data)
                    mp = MessageParam(
                        role="user",
                        content=[p],
                    )
                case IncludedImage():
                    p = self._prepare_imageblockparam(m.path)
                    mp = MessageParam(
                        role="user",
                        content=[p],
                    )
                case _:
                    pass
            if mp:
                output.append(mp)

        # If last message is user, apply prompt caching
        match output[-1]:
            case {"role": "user", "content": c}:
                print("applying prompt caching")
                output[-1] = MessageParam(
                    role="user",
                    content=[
                        TextBlockParam(
                            type="text",
                            text=c,
                            cache_control=CacheControlEphemeralParam(
                                type="ephemeral"
                            ),
                        )
                    ],
                )

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
    ) -> Generator[MessageChunk, None, None]:
        system_prompt, anth_messages = self._prepare_messages_for_model(
            messages
        )

        chunk_stream = self.c.messages.create(
            max_tokens=8192,
            messages=anth_messages,
            model=model,
            stream=True,
            system=system_prompt,
        )
        input_tokens = 0
        for event in chunk_stream:
            # logger.info(event.type)
            content = ""
            finish_reason = None
            output_tokens = None

            match event.type:
                case "message_start":
                    input_tokens = event.message.usage.input_tokens
                case "content_block_delta" if (
                    event.delta.type == "text_delta"
                ):
                    content = event.delta.text
                case "message_delta":
                    output_tokens = event.usage.output_tokens
                    match event.delta.stop_reason:
                        case "max_tokens":
                            finish_reason = FinishReason.Length
                        case _:
                            finish_reason = FinishReason.Stop

            yield MessageChunk(
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                finish_reason=finish_reason,
            )


class WatsonxAdaptor(ChatAdaptor):
    c: Optional[wai.APIClient]
    model_cache: Dict[str, waifm.ModelInference]
    models: List[str]
    apikey: str

    def __init__(self):
        self.c = None
        self.model_cache = {}

        if k := os.environ.get("WATSONX_IAM_API_KEY"):
            self.apikey = k
        else:
            raise MissingEnvVarException("WATSONX_IAM_API_KEY")

        if k := os.environ.get("WATSONX_PROJECT"):
            self.project_id = k
        else:
            raise MissingEnvVarException("WATSONX_PROJECT")

        # don't support this for now
        self.space_id = None

        # curate a decent set of models
        self.models = [
            "ibm/granite-3-8b-instruct",
            "meta-llama/llama-3-3-70b-instruct",
        ]

    def _client(self):
        if self.c:
            return self.c

        credentials = wai.Credentials(
            url="https://eu-gb.ml.cloud.ibm.com",
            api_key=self.apikey,
        )
        self.c = wai.APIClient(credentials)
        return self.c

    def list(self) -> List[str]:
        return self.models

    def supports_images(self, model: str) -> bool:
        return False

    def _model_inference(self, model: str) -> waifm.ModelInference:
        if m := self.model_cache.get(model):
            return m

        params = {
            "time_limit": 10000,
            "max_tokens": 10240,
        }
        verify = True
        fmodel = waifm.ModelInference(
            model_id=model,
            api_client=self._client(),
            params=params,
            project_id=self.project_id,
            space_id=self.space_id,
            verify=verify,
        )
        self.model_cache[model] = fmodel
        return fmodel

    def chat(
        self,
        model: str,
        messages: MessageList,
    ) -> Generator[MessageChunk, None, None]:
        messages_content = _prepare_messages_for_model(messages)
        fmodel = self._model_inference(model)
        try:
            stream_response = fmodel.chat_stream(messages=messages_content)
            for chunk in stream_response:
                content = ""
                input_tokens = None
                output_tokens = None
                finish_reason = None
                if ch := chunk.get("choices"):
                    content = ch[0]["delta"].get("content", "")
                    match ch[0]["finish_reason"]:
                        case "stop":
                            finish_reason = FinishReason.Stop
                        case "length":
                            finish_reason = FinishReason.Length
                        case None:
                            finish_reason = None
                        case _:
                            finish_reason = FinishReason.Other
                if chunk.get("usage"):
                    input_tokens = chunk["usage"]["total_tokens"]
                    output_tokens = 0  # TODO fix this per watsonx schema
                mc = MessageChunk(
                    content=content,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    finish_reason=finish_reason,
                )
                yield mc
        except WMLClientError as ex:
            raise ChatException(str(ex))
