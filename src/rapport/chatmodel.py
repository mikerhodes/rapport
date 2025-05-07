"""
General constants and types.

Trying to keep this indepdent from streamlit.
"""

from datetime import datetime
from pathlib import Path
from typing import Union, List, Optional, Literal, Annotated
from pydantic import BaseModel, Field

from rapport.appconfig import ConfigStore

PAGE_CHAT = "view_chat.py"
PAGE_HISTORY = "view_history.py"
PAGE_CONFIG = "view_config.py"
PAGE_HELP = "view_help.py"


class SystemMessage(BaseModel):
    message: str
    role: Literal["system"] = "system"
    type: Literal["SystemMessage"] = "SystemMessage"


class UserMessage(BaseModel):
    message: str
    role: Literal["user"] = "user"
    type: Literal["UserMessage"] = "UserMessage"


class AssistantMessage(BaseModel):
    message: str
    role: Literal["assistant"] = "assistant"
    type: Literal["AssistantMessage"] = "AssistantMessage"


class IncludedFile(BaseModel):
    name: str
    ext: str
    data: str
    role: Literal["user"] = "user"
    type: Literal["IncludedFile"] = "IncludedFile"


class IncludedImage(BaseModel):
    name: str
    path: Path
    role: Literal["user"] = "user"
    type: Literal["IncludedImage"] = "IncludedImage"


# This tells pydantic that the `type` field is used to figure
# out which of the message types to parse the JSON into.
Message = Annotated[
    Union[
        SystemMessage,
        UserMessage,
        AssistantMessage,
        IncludedFile,
        IncludedImage,
    ],
    Field(discriminator="type"),
]

MessageList = List[Message]


class Chat(BaseModel):
    model: str
    messages: MessageList
    created_at: datetime
    updated_at: datetime
    title: str = "New Chat"
    id: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    export_location: Optional[Path] = None
    input_tokens: int = 0
    output_tokens: int = 0


def new_chat(model: str, config_store: ConfigStore) -> Chat:
    """Initialise and return a new Chat"""

    # Get custom system prompt from config if available
    config = config_store.load_config()
    custom_prompt = config.custom_system_prompt

    system_message = get_system_message(custom_prompt)
    return Chat(
        model=model,
        messages=[
            system_message,
        ],
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


prompt_path = Path(__file__).parent / "systemprompt.md"
with open(prompt_path, "r") as file:
    default_system_prompt = file.read()


def get_system_message(extra_prompt=None):
    """Get system message, using custom prompt if provided"""
    system_prompt = default_system_prompt.format(
        extra_prompt=extra_prompt,
        current_date=datetime.now().strftime("%Y-%m-%d"),
    )
    # system_prompt = [
    #     extra_prompt if extra_prompt else default_system_prompt,
    #     "Use latex to render equations.",
    #     f"The current date is {datetime.today().isoformat()}.",
    # ]
    # system_prompt = "\n\n".join(system_prompt)
    return SystemMessage(message=system_prompt)


# Initialize with default system prompt
SYSTEM = get_system_message()
