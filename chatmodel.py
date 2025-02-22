"""
General constants and types.

Trying to keep this indepdent from streamlit.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

PAGE_CHAT = "view_chat.py"
PAGE_HISTORY = "view_history.py"


@dataclass
class Chat:
    model: str
    messages: List[Dict]
    created_at: datetime
    id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))


def new_chat(model: str) -> Chat:
    """Initialise and return a new Chat"""
    return Chat(
        model=model,
        messages=[SYSTEM],
        created_at=datetime.now(),
    )


with open("systemprompt.md", "r") as file:
    system_prompt = file.read()
SYSTEM = {
    "role": "system",
    "content": system_prompt,
}
