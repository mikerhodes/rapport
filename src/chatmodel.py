"""
General constants and types.

Trying to keep this indepdent from streamlit.
"""

from datetime import datetime
from pathlib import Path
from typing import Union, List, Optional, Literal
from pydantic import BaseModel, Field, field_serializer

PAGE_CHAT = "view_chat.py"
PAGE_HISTORY = "view_history.py"
PAGE_CONFIG = "view_config.py"


class BaseMessage(BaseModel):
    message: str
    role: str


class SystemMessage(BaseMessage):
    role: Literal["system"] = "system"


class UserMessage(BaseMessage):
    role: Literal["user"] = "user"


class AssistantMessage(BaseMessage):
    role: Literal["assistant"] = "assistant"


class IncludedFile(BaseMessage):
    role: Literal["user"] = "user"
    name: str
    ext: str
    data: str


MessageList = List[Union[AssistantMessage, UserMessage, SystemMessage, IncludedFile]]


class Chat(BaseModel):
    model: str
    messages: MessageList
    created_at: datetime
    updated_at: datetime
    title: str = "New Chat"
    id: str = Field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    export_location: Optional[Path] = None
    input_tokens: int = 0
    output_tokens: int = 0
    
    @field_serializer('export_location')
    def serialize_path(self, path: Optional[Path]) -> Optional[str]:
        return str(path) if path else None


def new_chat(model: str) -> Chat:
    """Initialise and return a new Chat"""
    return Chat(
        model=model,
        messages=[SYSTEM],
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


prompt_path = Path(__file__).parent / "systemprompt.md"
with open(prompt_path, "r") as file:
    system_prompt = file.read()
SYSTEM = SystemMessage(system_prompt)
