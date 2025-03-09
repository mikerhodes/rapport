"""
General constants and types.

Trying to keep this indepdent from streamlit.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Union, List

PAGE_CHAT = "view_chat.py"
PAGE_HISTORY = "view_history.py"


@dataclass
class AssistantMessage:
    message: str
    role: str = field(default="assistant")


@dataclass
class UserMessage:
    message: str
    role: str = field(default="user")


@dataclass
class IncludedFile:
    name: str
    ext: str
    data: str
    role: str = field(default="user")


@dataclass
class SystemMessage:
    message: str
    role: str = field(default="system")


type MessageList = List[
    Union[AssistantMessage, UserMessage, SystemMessage, IncludedFile]
]


@dataclass
class Chat:
    model: str
    messages: MessageList
    created_at: datetime
    title: str = field(default="New Chat")
    id: str = field(
        default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S")
    )


def new_chat(model: str) -> Chat:
    """Initialise and return a new Chat"""
    return Chat(
        model=model,
        messages=[SYSTEM],
        created_at=datetime.now(),
    )


with open("systemprompt.md", "r") as file:
    system_prompt = file.read()
SYSTEM = SystemMessage(system_prompt)
