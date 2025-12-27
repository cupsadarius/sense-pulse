"""Configuration loading and validation"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# Default config search paths (in order)
CONFIG_PATHS = [
    Path("config.yaml"),
    Path.home() / ".config" / "sense-pulse" / "config.yaml",
    Path("/etc/sense-pulse/config.yaml"),
]


@dataclass
class PiholeConfig:
    host: str = "http://localhost"
    password: str = ""  # App password from Pi-hole settings


@dataclass
class TailscaleConfig:
    cache_duration: int = 30


@dataclass
class DisplayConfig:
    rotation: int = 0
    show_icons: bool = True
    scroll_speed: float = 0.08
    icon_duration: float = 1.5


@dataclass
class SleepConfig:
    start_hour: int = 22
    end_hour: int = 7


@dataclass
class UpdateConfig:
    interval: int = 60


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "/var/log/sense-pulse.log"


@dataclass
class Config:
    pihole: PiholeConfig = field(default_factory=PiholeConfig)
    tailscale: TailscaleConfig = field(default_factory=TailscaleConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    sleep: SleepConfig = field(default_factory=SleepConfig)
    update: UpdateConfig = field(default_factory=UpdateConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def find_config_file() -> Optional[Path]:
    """Find config file in standard locations"""
    for path in CONFIG_PATHS:
        if path.exists():
            return path
    return None


def load_config(config_path: Optional[str] = None) -> Config:
    """Load configuration from YAML file"""
    if config_path:
        path = Path(config_path)
    else:
        path = find_config_file()

    if path is None or not path.exists():
        logger.warning("No config file found, using defaults")
        return Config()

    logger.info(f"Loading config from: {path}")

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    return Config(
        pihole=PiholeConfig(**data.get("pihole", {})),
        tailscale=TailscaleConfig(**data.get("tailscale", {})),
        display=DisplayConfig(**data.get("display", {})),
        sleep=SleepConfig(**data.get("sleep", {})),
        update=UpdateConfig(**data.get("update", {})),
        logging=LoggingConfig(**data.get("logging", {})),
    )
