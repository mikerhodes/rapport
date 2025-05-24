import logging
from typing import (
    Dict,
    Generator,
    List,
)

from rapport.chatmodel import (
    MessageList,
)
from rapport.tools import Tool

from .anthropic import AnthropicAdaptor
from .ollama import OllamaAdaptor
from .openai import OpenAIAdaptor
from .types import (
    ChatAdaptor,
    MessageChunk,
    MissingEnvVarException,
)
from .watsonx import WatsonxAdaptor

logger = logging.getLogger(__name__)


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
        tools: List[Tool],
    ) -> Generator[MessageChunk, None, None]:
        c = self.model_to_client[model]
        response = c.chat(
            model=model,
            messages=messages,
            tools=tools,
        )
        for chunk in response:
            yield chunk
