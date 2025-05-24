import logging
from typing import (
    Dict,
    List,
)

from rapport.chatmodel import (
    AssistantMessage,
    IncludedFile,
    MessageList,
    SystemMessage,
    UserMessage,
)


logger = logging.getLogger(__name__)


def prepare_messages_for_model(
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
