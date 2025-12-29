"""Tests for config module"""

import tempfile
from pathlib import Path

import pytest
import yaml

from sense_pulse.config import (
    Aranet4Config,
    Aranet4SensorConfig,
    AuthConfig,
    Config,
    DisplayConfig,
    LoggingConfig,
    PiholeConfig,
    SleepConfig,
    TailscaleConfig,
    UpdateConfig,
    WebConfig,
    find_config_file,
    load_config,
)


class TestConfigDataclasses:
    """Test configuration dataclasses"""

    def test_pihole_config_defaults(self):
        """Test PiholeConfig defaults"""
        config = PiholeConfig()
        assert config.host == "http://localhost"
        assert config.password == ""

    def test_display_config_defaults(self):
        """Test DisplayConfig defaults"""
        config = DisplayConfig()
        assert config.rotation == 0
        assert config.show_icons is True
        assert config.scroll_speed == 0.08
        assert config.icon_duration == 1.5

    def test_auth_config_defaults(self):
        """Test AuthConfig defaults"""
        config = AuthConfig()
        assert config.enabled is False
        assert config.username == "admin"
        assert config.password_hash == ""

    def test_aranet4_sensor_config(self):
        """Test Aranet4SensorConfig"""
        sensor = Aranet4SensorConfig(
            label="Office", mac_address="AA:BB:CC:DD:EE:FF", enabled=True
        )
        assert sensor.label == "Office"
        assert sensor.mac_address == "AA:BB:CC:DD:EE:FF"
        assert sensor.enabled is True


class TestConfigLoading:
    """Test configuration loading"""

    def test_load_config_with_defaults(self):
        """Test loading config returns defaults when no file exists"""
        config = load_config("/nonexistent/config.yaml")
        assert isinstance(config, Config)
        assert config.pihole.host == "http://localhost"
        assert config.web.port == 8080

    def test_load_config_from_yaml(self):
        """Test loading config from YAML file"""
        config_data = {
            "pihole": {"host": "http://pihole.local", "password": "secret"},
            "web": {"enabled": True, "host": "127.0.0.1", "port": 9090},
            "auth": {"enabled": True, "username": "testuser", "password_hash": "hash123"},
            "display": {"rotation": 90, "show_icons": False},
            "sleep": {"start_hour": 23, "end_hour": 6, "disable_pi_leds": True},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            config = load_config(config_path)

            assert config.pihole.host == "http://pihole.local"
            assert config.pihole.password == "secret"
            assert config.web.port == 9090
            assert config.web.host == "127.0.0.1"
            assert config.auth.enabled is True
            assert config.auth.username == "testuser"
            assert config.display.rotation == 90
            assert config.display.show_icons is False
            assert config.sleep.start_hour == 23
            assert config.sleep.disable_pi_leds is True
        finally:
            Path(config_path).unlink()

    def test_load_config_with_aranet4_sensors(self):
        """Test loading Aranet4 sensor configuration"""
        config_data = {
            "aranet4": {
                "timeout": 15,
                "cache_duration": 120,
                "sensors": [
                    {"label": "Office", "mac_address": "AA:BB:CC:DD:EE:FF", "enabled": True},
                    {
                        "label": "Bedroom",
                        "mac_address": "11:22:33:44:55:66",
                        "enabled": False,
                    },
                ],
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            config = load_config(config_path)

            assert config.aranet4.timeout == 15
            assert config.aranet4.cache_duration == 120
            assert len(config.aranet4.sensors) == 2
            assert config.aranet4.sensors[0].label == "Office"
            assert config.aranet4.sensors[0].mac_address == "AA:BB:CC:DD:EE:FF"
            assert config.aranet4.sensors[0].enabled is True
            assert config.aranet4.sensors[1].label == "Bedroom"
            assert config.aranet4.sensors[1].enabled is False
        finally:
            Path(config_path).unlink()

    def test_load_config_with_legacy_aranet4_format(self):
        """Test loading legacy Aranet4 format (office/bedroom keys)"""
        config_data = {
            "aranet4": {
                "office": {
                    "label": "Office",
                    "mac_address": "AA:BB:CC:DD:EE:FF",
                    "enabled": True,
                },
                "bedroom": {
                    "label": "Bedroom",
                    "mac_address": "11:22:33:44:55:66",
                    "enabled": False,
                },
                "timeout": 10,
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            config = load_config(config_path)

            # Should migrate to new format
            assert len(config.aranet4.sensors) == 2
            labels = [s.label for s in config.aranet4.sensors]
            assert "Office" in labels
            assert "Bedroom" in labels
        finally:
            Path(config_path).unlink()

    def test_load_config_with_partial_data(self):
        """Test loading config with only partial data uses defaults"""
        config_data = {"pihole": {"host": "http://custom.host"}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            config = load_config(config_path)

            assert config.pihole.host == "http://custom.host"
            assert config.pihole.password == ""  # Default
            assert config.web.port == 8080  # Default
            assert config.display.rotation == 0  # Default
        finally:
            Path(config_path).unlink()

    def test_find_config_file(self):
        """Test finding config file in standard locations"""
        # Create temp config in current directory
        config_path = Path("config.yaml")
        config_path.write_text("test: data")

        try:
            found = find_config_file()
            assert found == config_path
        finally:
            config_path.unlink()

    def test_find_config_file_not_found(self):
        """Test finding config file when none exists"""
        # Assuming no config in standard locations
        found = find_config_file()
        # May be None or a valid path depending on system
        assert found is None or isinstance(found, Path)
