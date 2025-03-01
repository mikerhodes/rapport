import json
from dataclasses import dataclass, asdict, replace, field
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    last_used_model: Optional[str] = field(default=None)


class ConfigStore:
    _path: Path

    def __init__(self, path: Path):
        self._path = path

    def save_config(self, config: Config):
        with open(self._path, "w") as f:
            json.dump(asdict(config), f)

    def load_config(self) -> Config:
        try:
            with open(self._path, "r") as f:
                data = json.load(f)
                return replace(Config(), **data)
        except FileNotFoundError:
            return Config()  # Return default config if file doesn't exist
