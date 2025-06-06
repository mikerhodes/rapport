import asyncio
from concurrent.futures import Future
import logging
import threading
from dataclasses import dataclass
from typing import Any, Coroutine, Dict, List, Optional, Callable

from fastmcp.client import StdioTransport
import httpx
from anthropic.types import ToolUnionParam
from fastmcp import Client

from rapport.appconfig import ConfigStore, StdioMCPServer, URLMCPServer

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class AsyncWorker:
    """
    Create a simple worker thread with its own asyncio.loop so we
    can safely call async code in a single event loop.

    Later, we can use this loop to set up our Client sessions such
    that we don't have to create new client sessions for every tool
    call (and, particularly, re-execute stdio MCP servers).
    """

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._start_loop, daemon=True)
        self.thread.start()

    def _start_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro: Coroutine) -> Any:
        future: Future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    def stop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()


@dataclass
class Tool:
    name: str
    description: str
    function_name: str
    parameters: Dict[str, Any]  # JSON schema for parameters
    server: URLMCPServer | StdioMCPServer
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


class ToolRegistry:
    def __init__(self):
        self._client_cache: Dict[str, Any] = {}
        self.tools: Dict[str, Tool] = {}  # Tool.name : Tool
        self._tools_lock = threading.Lock()
        self._initialised = False
        self.worker = AsyncWorker()

    # To create a thing where instead each Client is connected
    # and running, we could use an approach where we have
    # an infinite loop running on a async function for each
    # client. It pulls a tuple of (data, response_queue) from
    # its input queue, and replies on response_queue.
    # We'd instead store the input queues in something like client_cache
    # Shutting down, we'd send None on the queue perhaps.
    # See Claude chat.

    def _get_client_sync(
        self, server: URLMCPServer | StdioMCPServer
    ) -> Client:
        if server.id not in self._client_cache:
            logger.debug("Creating Client for %s", server)
            match server:
                case URLMCPServer():
                    self._client_cache[server.id] = Client(server.url)
                case StdioMCPServer():
                    self._client_cache[server.id] = Client(
                        StdioTransport(server.command, server.args)
                    )
            logger.debug("Created Client for %s", server)
        client = self._client_cache[server.id]
        logger.debug("Returning client %s for %s", client, server)
        return client

    async def _list_tools(
        self, server: URLMCPServer | StdioMCPServer
    ) -> List[Any]:
        # client = await self._get_client(server)
        client = self._client_cache[server.id]

        try:
            logger.debug("Connecting to %s", server)
            async with client:
                logger.debug(f"Client connected: {client.is_connected()}")

                # Make MCP calls within the context
                tools = await client.list_tools()
            logger.debug("Completed _list_tools: %s", server)
            return tools
        except ProcessLookupError as ex:
            logger.error("Error calling MCP server: %s", ex)
            return []
        except Exception as ex:
            logger.error("Error calling MCP server: %s", ex)
            return []

    async def _run_tool(self, tool: Tool, params: Dict[str, Any]) -> str:
        # client = await self._get_client(server)
        client = self._client_cache[tool.server.id]
        result = None

        try:
            async with client:
                logger.debug(f"Client connected: {client.is_connected()}")

                # Make MCP calls within the context
                tools = await client.list_tools()

                if any(t.name == tool.name for t in tools):
                    result = await client.call_tool(tool.name, params)

            if result is not None:
                return "\n".join(
                    [x.text for x in result if x.type == "text"]
                )
            else:
                return ""
        except ProcessLookupError as ex:
            logger.error("Error calling MCP server: %s", ex)
            return ""

    def _get_available_tools(
        self, s: URLMCPServer | StdioMCPServer
    ) -> List[Tool]:
        """Return all available tools"""
        logger.debug("Starting _list_tools: %s", s)
        try:
            tools = self.worker.submit(self._list_tools(s))
        except httpx.HTTPError as ex:
            logger.warning("MCP server %s unreachable: %s", s, ex)
            tools = []
        logger.debug("Completed _list_tools: %s", s)

        return [
            Tool(
                name=x.name,
                description=x.description or "",
                function_name=x.name,
                parameters=x.inputSchema,
                server=s,
            )
            for x in tools
        ]

    def _iterate_enabled_tools(self, config: ConfigStore):
        mcp_servers = config.load_config().mcp_servers
        seen_tools = set()  # no dup tool names
        # Find URL where tool is available and allowed
        for n, s in mcp_servers.items():
            logger.debug("Processing MCP server: %s", s)

            self._client_cache[s.id] = self._get_client_sync(s)

            # Don't enable any tools if there are duplicate names
            available_tools = self._get_available_tools(s)
            logger.debug("got available_tools for: %s", s)
            for n in [x.name for x in available_tools]:
                if n in seen_tools:
                    logger.error(
                        "Duplicate tool name, disabling tools: %s", n
                    )
                    raise ValueError(
                        "Duplicate tool name, disabling tools: " + n
                    )
                seen_tools.add(n)

            allowed_tools = [x.strip() for x in s.allowed_tools]
            if allowed_tools and available_tools:
                for x in [
                    x for x in available_tools if x.name in allowed_tools
                ]:
                    yield x

    def initialise_tools(self, config: ConfigStore):
        """
        Initialise availabe tools from config.

        Safe to call repeatedly. Once called, subsequent calls
        will be noops.
        """
        if self._initialised:
            return
        new_tools: Dict[str, Tool] = {}
        for tool in self._iterate_enabled_tools(config=config):
            new_tools[tool.name] = tool
            logger.debug("added tool: %s: %s", tool.name, tool.server)
        with self._tools_lock:
            self.tools = new_tools
        self._initialised = True

    def get_enabled_tools(self) -> List[Tool]:
        """Return only enabled tools based on their names"""
        if not self._initialised:
            raise RuntimeError("Tools not initialised")

        ts: List[Tool] = []
        with self._tools_lock:
            for tool in self.tools.values():
                ts.append(tool)
        return ts

    def _get_tool(self, name: str) -> Optional[Tool]:
        with self._tools_lock:
            t = self.tools.get(name, None)
            return t

    def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> str:
        """Execute a tool with the given parameters"""
        if not self._initialised:
            raise RuntimeError("Tools not initialised")

        tool = self._get_tool(tool_name)
        if tool is None:
            raise ValueError(f"Unknown tool: {tool_name}")

        # validate correct params?

        result = self.worker.submit(self._run_tool(tool, params))
        return result or ""
