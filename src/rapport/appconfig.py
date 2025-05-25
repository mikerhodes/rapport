import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class URLMCPServer(BaseModel):
    url: str
    allowed_tools: List[str]

    @property
    def id(self):
        return self.url

    def __str__(self) -> str:
        return f"URLMCPServer[{self.url}]"


class StdioMCPServer(BaseModel):
    command: str
    args: List[str]
    allowed_tools: List[str]

    @property
    def id(self):
        return self.command + "-" + "-".join(self.args)

    def __str__(self) -> str:
        return f"StdioMCPServer[{self.command} {' '.join(self.args)}]"


type MCPServerList = Dict[str, URLMCPServer | StdioMCPServer]


class Config(BaseModel):
    preferred_model: Optional[str] = None
    obsidian_directory: Optional[str] = None
    last_used_model: Optional[str] = None
    custom_system_prompt: Optional[str] = None
    mcp_servers: MCPServerList = {}


class ConfigStore:
    _path: Path

    def __init__(self, path: Path):
        self._path = path

    def save_config(self, config: Config):
        data = config.model_dump_json()
        with open(self._path, "w") as f:
            f.write(data)

    def load_config(self) -> Config:
        try:
            with open(self._path, "r") as f:
                data = json.load(f)
                return Config(**data)
        except FileNotFoundError:
            logger.warning(
                "Couldn't load config from %s; loading default", self._path
            )
            return Config()  # Return default config if file doesn't exist
