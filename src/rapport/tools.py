from dataclasses import dataclass
from typing import Dict, List, Callable, Any

from anthropic.types import ToolUnionParam

import asyncio
from fastmcp import Client

client = Client("http://localhost:9000/mcp")


async def list_tools():
    # Connection is established here
    async with client:
        print(f"Client connected: {client.is_connected()}")

        # Make MCP calls within the context
        tools = await client.list_tools()

        if any(tool.name == "add" for tool in tools):
            result = await client.call_tool("add", {"a": 123, "b": 456})
            print(f"Add result: {result}")

    return tools


async def run_tool(name: str, params: Dict[str, Any]):
    result = None

    async with client:
        print(f"Client connected: {client.is_connected()}")

        # Make MCP calls within the context
        tools = await client.list_tools()

        if any(tool.name == name for tool in tools):
            result = await client.call_tool(name, params)

    if result is not None:
        return "\n".join([x.text for x in result if x.type == "text"])


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
# Perhaps we'd want some "standard" tools here, eg search duckduckgo or read url
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
    tools = asyncio.run(list_tools())
    return [
        Tool(
            name=x.name,
            description=x.description or "",
            function_name=x.name,
            parameters=x.inputSchema,
        )
        for x in tools
    ]
    # return list(AVAILABLE_TOOLS.values())


def get_enabled_tools(enabled_tool_names: List[str]) -> List[Tool]:
    """Return only enabled tools based on their names"""
    # all tools until we write config
    # perhaps config can be like:
    # server toolname,toolname
    # http://localhost:1234/mcp add,mul
    # if the servers are up, they are available, filter on tool names
    return [t for t in get_available_tools()]
    # return [t for t in get_available_tools() if t.name in enabled_tool_names]


def execute_tool(tool_name: str, params: Dict[str, Any]) -> str:
    """Execute a tool with the given parameters"""
    if tool_name not in [x.name for x in get_enabled_tools([])]:
        raise ValueError(f"Unknown tool: {tool_name}")

    # validate correct params?

    # func = TOOL_FUNCTIONS[tool_name]
    # return str(func(**params))

    result = asyncio.run(run_tool(tool_name, params))
    return result or ""
