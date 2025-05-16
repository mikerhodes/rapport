from dataclasses import dataclass
import threading
from typing import Dict, List, Any, Optional

from anthropic.types import ToolUnionParam

import asyncio
from fastmcp import Client

from rapport.appconfig import ConfigStore

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

_client_cache: Dict[str, Any] = {}
_client_cache_lock = threading.Lock()


async def list_tools(mcp_url: str):
    with _client_cache_lock:
        if mcp_url not in _client_cache:
            logger.debug("Creating Client for %s", mcp_url)
            _client_cache[mcp_url] = Client(mcp_url)
        client = _client_cache[mcp_url]

    # Connection is established here
    async with client:
        logger.debug(f"Client connected: {client.is_connected()}")

        # Make MCP calls within the context
        tools = await client.list_tools()

    return tools


async def run_tool(mcp_url: str, name: str, params: Dict[str, Any]):
    with _client_cache_lock:
        if mcp_url not in _client_cache:
            logger.debug("Creating Client for %s", mcp_url)
            _client_cache[mcp_url] = Client(mcp_url)
        client = _client_cache[mcp_url]
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


def _iterate_enabled_tools(config: ConfigStore):
    mcp_servers = config.load_config().mcp_servers.splitlines()
    seen_tools = set()  # no dup tool names
    # Find URL where tool is available and allowed
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
        if allowed_tools and available_tools:
            for x in [x for x in available_tools if x.name in allowed_tools]:
                yield url, x


def get_enabled_tools(config: ConfigStore) -> List[Tool]:
    """Return only enabled tools based on their names"""
    ts: List[Tool] = []
    for _, tool in _iterate_enabled_tools(config=config):
        ts.append(tool)
    logger.debug("enabled_tools %s", ts)
    return ts


def _url_for_tool(config: ConfigStore, name: str) -> Optional[str]:
    for url, tool in _iterate_enabled_tools(config=config):
        if name == tool.name:
            return url
    return None


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
