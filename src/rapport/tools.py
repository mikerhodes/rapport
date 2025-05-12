from dataclasses import dataclass
from typing import Dict, List, Callable, Any

from anthropic.types import ToolUnionParam


@dataclass
class Tool:
    name: str
    description: str
    function_name: str
    parameters: Dict[str, Any]  # JSON schema for parameters
    enabled: bool = True

    def render_openai(self) -> Dict[str, Any]:
        """Return the commonly used openai tool schema for this tool"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def render_anthropic(self) -> ToolUnionParam:
        """Return the anthropic-specific tool schema for this tool"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


def add(a: int, b: int) -> int:
    """Add two integers and return their sum."""
    return a + b


# Define tools with metadata
AVAILABLE_TOOLS = {
    "add": Tool(
        name="add",
        description="Add two integers together",
        function_name="add",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "integer", "description": "First number"},
                "b": {"type": "integer", "description": "Second number"},
            },
            "required": ["a", "b"],
        },
    )
}

# Map function names to actual functions
TOOL_FUNCTIONS: Dict[str, Callable] = {"add": add}


def get_available_tools() -> List[Tool]:
    """Return all available tools"""
    return list(AVAILABLE_TOOLS.values())


def get_enabled_tools(enabled_tool_names: List[str]) -> List[Tool]:
    """Return only enabled tools based on their names"""
    # all tools until we write config
    return [t for t in get_available_tools()]
    # return [t for t in get_available_tools() if t.name in enabled_tool_names]


def execute_tool(tool_name: str, params: Dict[str, Any]) -> Any:
    """Execute a tool with the given parameters"""
    if tool_name not in TOOL_FUNCTIONS:
        raise ValueError(f"Unknown tool: {tool_name}")

    # validate correct params?

    func = TOOL_FUNCTIONS[tool_name]
    return func(**params)
