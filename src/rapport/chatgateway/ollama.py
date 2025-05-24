import logging
from typing import (
    Generator,
    List,
    Optional,
)

import ollama

from rapport.chatmodel import (
    MessageList,
)
from rapport.tools import Tool

from .common import (
    prepare_messages_for_model,
)
from .types import ChatAdaptor, FinishReason, MessageChunk, ModelInfo

logger = logging.getLogger(__name__)


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
        tools: List[Tool],
    ) -> Generator[MessageChunk, None, None]:
        messages_content = prepare_messages_for_model(messages)
        m = self._show(model)
        if m is None:
            logger.error("Ollama chat got unknown model: %s", model)
            return
        # Truncate the context length to reduce memory usage
        # TODO make this an option?
        num_ctx = min(2048, m.context_length)

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
                tool_call=None,
            )
