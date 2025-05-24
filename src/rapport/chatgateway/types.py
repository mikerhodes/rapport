import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import (
    Generator,
    List,
    Optional,
    Protocol,
)


from rapport.chatmodel import (
    MessageList,
    ToolCallMessage,
)
from rapport.tools import Tool

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
    tool_call: Optional[ToolCallMessage]


class ChatAdaptor(Protocol):
    """ChatAdaptor adapts an LLM interface to ChatGateway's expectations."""

    def list(self) -> List[str]: ...

    def supports_images(self, model: str) -> bool: ...

    def chat(
        self,
        model: str,
        messages: MessageList,
        tools: List[Tool],
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
