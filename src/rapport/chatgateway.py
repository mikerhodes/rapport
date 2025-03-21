import os
from dataclasses import dataclass
from enum import Enum, auto
import logging
from typing import Dict, Generator, List, Optional, Protocol

import ibm_watsonx_ai as wai
import ibm_watsonx_ai.foundation_models as waifm
import ollama
from anthropic import Anthropic
from anthropic.types import MessageParam
from ibm_watsonx_ai.wml_client_error import WMLClientError

from rapport.chatmodel import (
    AssistantMessage,
    IncludedFile,
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

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
    ) -> Generator[MessageChunk, None, None]: ...


class MissingEnvVarException(Exception):
    def __str__(self) -> str:
        return f"Missing env var: {self.args[0]}"


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

    def list(self) -> List[str]:
        return self.models

    def chat(
        self,
        model: str,
        messages: MessageList,
    ) -> Generator[MessageChunk, None, None]:
        c = self.model_to_client[model]
        response = c.chat(
            model=model,
            messages=_prepare_messages_for_model(messages),
        )
        for chunk in response:
            yield chunk


def _prepare_messages_for_model(
    messages: MessageList,
) -> List[Dict[str, str]]:
    """
    Converts message history format into format for model.
    This implementation is generic. More advanced versions could
    be implemented for multi-modal models like Claude.
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
        # Models don't have a file role, so convert
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
        messages: List[Dict[str, str]],
    ) -> Generator[MessageChunk, None, None]:
        m = self._show(model)
        if m is None:
            logger.error("Ollama chat got unknown model: %s", model)
            return
        # Truncate the context length to reduce memory usage
        # TODO make this an option?
        num_ctx = min(8192, m.context_length)

        response = self.c.chat(
            model=model,
            messages=messages,
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


class AnthropicAdaptor(ChatAdaptor):
    models: List[str]
    c: Anthropic

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

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
    ) -> Generator[MessageChunk, None, None]:
        system_prompt = "\n\n".join(
            [m["content"] for m in messages if m["role"] == "system"]
        )
        anth_messages = [
            MessageParam(role=m["role"], content=m["content"])  # type: ignore
            for m in messages
            if m["role"] in ["user", "assistant"]
        ]
        chunk_stream = self.c.messages.create(
            max_tokens=2048,
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
    models: List[str]
    apikey: str

    def __init__(self):
        self.c = None

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

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
    ) -> Generator[MessageChunk, None, None]:
        params = {
            "time_limit": 10000,
            "max_tokens": 4096,
        }  # hopefully enough tokens

        verify = True
        fmodel = waifm.ModelInference(
            model_id=model,
            api_client=self._client(),
            params=params,
            project_id=self.project_id,
            space_id=self.space_id,
            verify=verify,
        )

        try:
            stream_response = fmodel.chat_stream(messages=messages)
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
