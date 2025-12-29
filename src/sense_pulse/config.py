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
    web_rotation_offset: int = 90  # Offset for web preview to match physical display


@dataclass
class SleepConfig:
    start_hour: int = 22
    end_hour: int = 7
    disable_pi_leds: bool = False  # Disable Pi onboard LEDs (PWR/ACT) during sleep


@dataclass
class UpdateConfig:
    interval: int = 60


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "/var/log/sense-pulse.log"


@dataclass
class WebConfig:
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8080


@dataclass
class AuthConfig:
    """Authentication configuration for web dashboard"""
    enabled: bool = False
    username: str = "admin"
    password_hash: str = ""  # Bcrypt hash of password


@dataclass
class Aranet4SensorConfig:
    """Configuration for a single Aranet4 sensor"""
    label: str = ""
    mac_address: str = ""
    enabled: bool = False


@dataclass
class Aranet4Config:
    """Configuration for Aranet4 CO2 sensors"""
    sensors: list = field(default_factory=list)  # List of Aranet4SensorConfig
    timeout: int = 10  # Connection timeout in seconds
    cache_duration: int = 60  # Cache readings for this many seconds


@dataclass
class Config:
    pihole: PiholeConfig = field(default_factory=PiholeConfig)
    tailscale: TailscaleConfig = field(default_factory=TailscaleConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    sleep: SleepConfig = field(default_factory=SleepConfig)
    update: UpdateConfig = field(default_factory=UpdateConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    web: WebConfig = field(default_factory=WebConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    aranet4: Aranet4Config = field(default_factory=Aranet4Config)


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

    # Parse Aranet4 config with sensor list (migrate old office/bedroom format)
    aranet4_data = data.get("aranet4", {})
    sensors = []

    # New format: sensors list
    if "sensors" in aranet4_data:
        for sensor_data in aranet4_data["sensors"]:
            sensors.append(Aranet4SensorConfig(**sensor_data))
    # Old format migration: office/bedroom
    else:
        if "office" in aranet4_data and aranet4_data["office"].get("mac_address"):
            office = aranet4_data["office"]
            sensors.append(Aranet4SensorConfig(
                label=office.get("label", "Office"),
                mac_address=office.get("mac_address", ""),
                enabled=office.get("enabled", False),
            ))
        if "bedroom" in aranet4_data and aranet4_data["bedroom"].get("mac_address"):
            bedroom = aranet4_data["bedroom"]
            sensors.append(Aranet4SensorConfig(
                label=bedroom.get("label", "Bedroom"),
                mac_address=bedroom.get("mac_address", ""),
                enabled=bedroom.get("enabled", False),
            ))

    aranet4_config = Aranet4Config(
        sensors=sensors,
        timeout=aranet4_data.get("timeout", 10),
        cache_duration=aranet4_data.get("cache_duration", 60),
    )

    return Config(
        pihole=PiholeConfig(**data.get("pihole", {})),
        tailscale=TailscaleConfig(**data.get("tailscale", {})),
        display=DisplayConfig(**data.get("display", {})),
        sleep=SleepConfig(**data.get("sleep", {})),
        update=UpdateConfig(**data.get("update", {})),
        logging=LoggingConfig(**data.get("logging", {})),
        web=WebConfig(**data.get("web", {})),
        auth=AuthConfig(**data.get("auth", {})),
        aranet4=aranet4_config,
    )
