import os
from dataclasses import dataclass
from typing import Dict, Generator, List, Protocol, Union

from anthropic.types import MessageParam
import ollama
from anthropic import Anthropic


@dataclass
class ModelInfo:
    name: str
    context_length: int


@dataclass
class MessageChunk:
    used_tokens: Union[int, None]
    content: str


class ChatAdaptor(Protocol):
    """ChatAdaptor adapts an LLM interface to ChatGateway's expectations."""

    def show(self, model: str) -> Union[ModelInfo, None]: ...

    def list(self) -> List[str]: ...

    def chat(
        self, model: str, messages: List[Dict[str, str]], stream: bool, num_ctx: int
    ) -> Generator[MessageChunk, None, None]: ...


class ChatGateway:
    models: List[str]
    model_to_client: Dict[str, ChatAdaptor]

    def __init__(self):
        """Load up the available models"""
        self.models = []
        self.model_to_client = {}

        oa = OllamaAdaptor()
        self.models.extend(oa.list())
        for m in oa.list():
            self.model_to_client[m] = oa

        if os.environ.get("ANTHROPIC_API_KEY"):
            aa = AnthropicAdaptor()
            self.models.extend(aa.list())
            for m in aa.list():
                self.model_to_client[m] = aa

    def list(self) -> List[str]:
        return self.models

    def chat(
        self, model: str, messages: List[Dict[str, str]], stream: bool, num_ctx: int
    ) -> Generator[MessageChunk, None, None]:
        c = self.model_to_client[model]
        response = c.chat(
            model=model,
            messages=messages,
            stream=True,
            num_ctx=num_ctx,
        )
        for chunk in response:
            yield chunk

    def show(self, model: str) -> Union[ModelInfo, None]:
        c = self.model_to_client[model]
        return c.show(model)


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

    def show(self, model: str) -> Union[ModelInfo, None]:
        m = self.c.show(model)
        if m and m.modelinfo and m.details:
            return ModelInfo(model, m.modelinfo[f"{m.details.family}.context_length"])
        else:
            return None

    def chat(
        self, model: str, messages: List[Dict[str, str]], stream: bool, num_ctx: int
    ) -> Generator[MessageChunk, None, None]:
        response = self.c.chat(
            model=model,
            messages=messages,
            stream=True,
            options=ollama.Options(
                num_ctx=num_ctx,
            ),
        )
        for chunk in response:
            if chunk.prompt_eval_count and chunk.eval_count:
                mc = MessageChunk(
                    content=chunk["message"]["content"],
                    used_tokens=chunk.prompt_eval_count + chunk.eval_count,
                )
            else:
                mc = MessageChunk(content=chunk["message"]["content"], used_tokens=None)
            yield mc


class AnthropicAdaptor(ChatAdaptor):
    models: List[str]
    c: Anthropic

    def __init__(self):
        # For now we hardcode Claude models we want to use
        # while we firm up how ChatGateway should work.
        self.models = ["claude-3-5-haiku-latest", "claude-3-5-sonnet-latest"]
        self.c = Anthropic()

    def list(self) -> List[str]:
        return self.models

    def show(self, model: str) -> Union[ModelInfo, None]:
        return ModelInfo(model, 200_000)

    def chat(
        self, model: str, messages: List[Dict[str, str]], stream: bool, num_ctx: int
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
            max_tokens=1024,
            messages=anth_messages,
            model=model,
            stream=True,
            system=system_prompt,
        )
        for event in chunk_stream:
            # print(event.type)
            if event.type == "content_block_delta" and event.delta.type == "text_delta":
                yield MessageChunk(content=event.delta.text, used_tokens=None)
            elif event.type == "message_delta":
                yield MessageChunk(content="", used_tokens=event.usage.output_tokens)
