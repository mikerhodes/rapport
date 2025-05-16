from dataclasses import dataclass
from typing import Dict, List, Callable, Any, Optional

from anthropic.types import ToolUnionParam

import asyncio
from fastmcp import Client

from rapport.appconfig import ConfigStore

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


async def list_tools(mcp_url: str):
    client = Client(mcp_url)

    # Connection is established here
    async with client:
        logger.debug(f"Client connected: {client.is_connected()}")

        # Make MCP calls within the context
        tools = await client.list_tools()

    return tools


async def run_tool(mcp_url: str, name: str, params: Dict[str, Any]):
    client = Client(mcp_url)
    result = None

    async with client:
        logger.debug(f"Client connected: {client.is_connected()}")

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


def get_available_tools(mcp_url: str) -> List[Tool]:
    """Return all available tools"""
    tools = asyncio.run(list_tools(mcp_url))
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


def get_enabled_tools(config: ConfigStore) -> List[Tool]:
    """Return only enabled tools based on their names"""
    mcp_servers = config.load_config().mcp_servers.splitlines()
    enabled_tools: List[Tool] = []
    seen_tools = set()  # no dup tool names
    for s in mcp_servers:
        logger.debug("Processing MCP server: %s", s)
        url, ts = s.split(" ", 1)
        logger.debug("Extracted URL: %s", url)

        # Don't enable any tools if there are duplicate names
        available_tools = get_available_tools(url)
        for n in [x.name for x in available_tools]:
            if n in seen_tools:
                logger.error("Duplicate tool name, disabling tools: %s", n)
                raise ValueError(
                    "Duplicate tool name, disabling tools: " + n
                )
            seen_tools.add(n)

        allowed_tools = [x.strip() for x in ts.split(",")]
        logger.debug("%s allowed_tools %s", url, allowed_tools)
        if allowed_tools:
            if available_tools:
                enabled_tools.extend(
                    x for x in available_tools if x.name in allowed_tools
                )
        logger.debug(
            "Updated enabled_tools: %s", [x.name for x in enabled_tools]
        )
    # all tools until we write config
    # perhaps config can be like:
    # server toolname,toolname
    # http://localhost:1234/mcp add,mul
    # if the servers are up, they are available, filter on tool names
    logger.debug("Final enabled_tools: %s", [x.name for x in enabled_tools])
    return enabled_tools


def _url_for_tool(config: ConfigStore, name: str) -> Optional[str]:
    url = None

    mcp_servers = config.load_config().mcp_servers.splitlines()
    seen_tools = set()  # no dup tool names
    # Find URL where tool is available and allowed
    for s in mcp_servers:
        enabled_tools: List[Tool] = []
        logger.debug("Processing MCP server: %s", s)
        url, ts = s.split(" ", 1)
        logger.debug("Extracted URL: %s", url)

        # Don't enable any tools if there are duplicate names
        available_tools = get_available_tools(url)
        for n in [x.name for x in available_tools]:
            if n in seen_tools:
                logger.error("Duplicate tool name, disabling tools: %s", n)
                raise ValueError(
                    "Duplicate tool name, disabling tools: " + n
                )
            seen_tools.add(n)

        allowed_tools = [x.strip() for x in ts.split(",")]
        logger.debug("%s allowed_tools %s", url, allowed_tools)
        if allowed_tools:
            if available_tools:
                enabled_tools.extend(
                    x for x in available_tools if x.name in allowed_tools
                )

        if name in [x.name for x in enabled_tools]:
            return url
        logger.debug(
            "Updated enabled_tools: %s", [x.name for x in enabled_tools]
        )
    return url


def execute_tool(
    config: ConfigStore, tool_name: str, params: Dict[str, Any]
) -> str:
    """Execute a tool with the given parameters"""
    mcp_url = _url_for_tool(config, tool_name)
    if mcp_url is None:
        raise ValueError(f"Unknown tool: {tool_name}")

    # validate correct params?
    result = asyncio.run(run_tool(mcp_url, tool_name, params))
    return result or ""
