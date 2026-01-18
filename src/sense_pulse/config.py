"""Configuration loading and validation"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from .web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="config")

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
class CacheConfig:
    """Configuration for data cache polling"""

    ttl: float = 60.0  # Cache time-to-live in seconds
    poll_interval: float = 30.0  # Background poll interval in seconds


@dataclass
class WeatherConfig:
    """Configuration for weather data source"""

    enabled: bool = True
    location: str = ""  # Location for weather (e.g., "London", "New York", "~Eiffel+Tower")
    cache_duration: int = 300  # Cache weather data for 5 minutes (API updates hourly)


@dataclass
class BabyMonitorConfig:
    """Configuration for baby monitor RTSP stream"""

    enabled: bool = False
    rtsp_url: str = ""  # RTSP URL (e.g., "rtsp://admin:admin@192.168.1.111:8554/...")
    transport: str = "tcp"  # tcp or udp
    reconnect_delay: int = 5  # Seconds to wait before reconnecting
    max_reconnect_attempts: int = -1  # -1 for infinite
    hls_segment_duration: int = 2  # HLS segment duration in seconds
    hls_playlist_size: int = 3  # Number of segments in playlist
    output_dir: str = "/tmp/sense-pulse/hls"  # Directory for HLS segments


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
    cache: CacheConfig = field(default_factory=CacheConfig)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    baby_monitor: BabyMonitorConfig = field(default_factory=BabyMonitorConfig)


def find_config_file() -> Optional[Path]:
    """Find config file in standard locations"""
    for path in CONFIG_PATHS:
        if path.exists():
            return path
    return None


def load_config(config_path: Optional[str] = None) -> Config:
    """Load configuration from YAML file"""
    path = Path(config_path) if config_path else find_config_file()

    if path is None or not path.exists():
        logger.warning("No config file found, using defaults")
        return Config()

    logger.info("Loading config", path=str(path))

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
            sensors.append(
                Aranet4SensorConfig(
                    label=office.get("label", "Office"),
                    mac_address=office.get("mac_address", ""),
                    enabled=office.get("enabled", False),
                )
            )
        if "bedroom" in aranet4_data and aranet4_data["bedroom"].get("mac_address"):
            bedroom = aranet4_data["bedroom"]
            sensors.append(
                Aranet4SensorConfig(
                    label=bedroom.get("label", "Bedroom"),
                    mac_address=bedroom.get("mac_address", ""),
                    enabled=bedroom.get("enabled", False),
                )
            )

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
        cache=CacheConfig(**data.get("cache", {})),
        weather=WeatherConfig(**data.get("weather", {})),
        baby_monitor=BabyMonitorConfig(**data.get("baby_monitor", {})),
    )
