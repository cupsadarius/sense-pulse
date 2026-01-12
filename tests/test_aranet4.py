"""Tests for Aranet4 BLE device and sensor classes"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from sense_pulse.config import Aranet4Config, Aranet4SensorConfig
from sense_pulse.datasources.aranet4_source import Aranet4DataSource
from sense_pulse.devices.aranet4 import Aranet4Device, Aranet4Reading, Aranet4Sensor


class TestAranet4Device:
    """Test Aranet4Device class"""

    def test_init_creates_lock_and_empty_sensors(self):
        """Device initializes with lock and empty sensor dict"""
        device = Aranet4Device()
        assert isinstance(device._lock, asyncio.Lock)
        assert device.sensors == {}

    def test_add_sensor(self):
        """add_sensor registers sensor by label"""
        device = Aranet4Device()
        sensor = Aranet4Sensor("AA:BB:CC:DD:EE:FF", "test")
        device.add_sensor("office", sensor)

        assert device.get_sensor("office") is sensor
        assert "office" in device.sensors

    def test_get_sensor_returns_none_for_unknown(self):
        """get_sensor returns None for unknown label"""
        device = Aranet4Device()
        assert device.get_sensor("unknown") is None

    @pytest.mark.asyncio
    async def test_read_all_sensors_empty_when_no_sensors(self):
        """read_all_sensors returns empty dict when no sensors configured"""
        device = Aranet4Device()
        results = await device.read_all_sensors()
        assert results == {}

    @pytest.mark.asyncio
    async def test_read_all_sensors_via_scan(self):
        """read_all_sensors uses BLE scan to get readings"""
        device = Aranet4Device()
        sensor1 = Aranet4Sensor("AA:BB:CC:DD:EE:FF", "office")
        sensor2 = Aranet4Sensor("11:22:33:44:55:66", "bedroom")
        device.add_sensor("office", sensor1)
        device.add_sensor("bedroom", sensor2)

        # Mock aranet4 scan - only find first sensor
        mock_advertisement = Mock()
        mock_advertisement.device.address = "AA:BB:CC:DD:EE:FF"
        mock_advertisement.readings = Mock(
            co2=800,
            temperature=22.5,
            humidity=50,
            pressure=1013.0,
            battery=90,
            interval=300,
            ago=10,
        )

        async def mock_find_nearby(callback, duration):
            callback(mock_advertisement)

        with patch("aranet4.client._find_nearby", new=mock_find_nearby):
            results = await device.read_all_sensors()

        assert results["office"] is not None
        assert results["office"].co2 == 800
        assert results["office"].temperature == 22.5
        assert results["office"].humidity == 50
        assert results["office"].pressure == 1013.0
        assert results["office"].battery == 90
        assert results["bedroom"] is None  # not found in scan

    @pytest.mark.asyncio
    async def test_read_all_sensors_handles_import_error(self):
        """read_all_sensors returns empty results on ImportError"""
        device = Aranet4Device()
        sensor = Aranet4Sensor("AA:BB:CC:DD:EE:FF", "office")
        device.add_sensor("office", sensor)

        with (
            patch.dict("sys.modules", {"aranet4": None}),
            patch(
                "sense_pulse.devices.aranet4.Aranet4Device.read_all_sensors",
                new_callable=AsyncMock,
                return_value={"office": None},
            ),
        ):
            results = await device.read_all_sensors()
            assert results["office"] is None

    @pytest.mark.asyncio
    async def test_scan_for_devices_returns_empty_on_import_error(self):
        """scan_for_devices returns empty list if aranet4 not installed"""
        device = Aranet4Device()

        with (
            patch.dict("sys.modules", {"aranet4": None}),
            patch(
                "sense_pulse.devices.aranet4.Aranet4Device.scan_for_devices",
                return_value=[],
            ),
        ):
            result = await device.scan_for_devices()
            assert result == []


class TestAranet4Sensor:
    """Test Aranet4Sensor class"""

    def test_init_uppercases_mac(self):
        """MAC address is uppercased on init"""
        sensor = Aranet4Sensor("aa:bb:cc:dd:ee:ff", "office")
        assert sensor.mac_address == "AA:BB:CC:DD:EE:FF"

    def test_init_defaults(self):
        """Default values are set correctly"""
        sensor = Aranet4Sensor("AA:BB:CC:DD:EE:FF")
        assert sensor.name == "sensor"
        assert sensor.mac_address == "AA:BB:CC:DD:EE:FF"

    def test_init_with_name(self):
        """Name is set correctly"""
        sensor = Aranet4Sensor("AA:BB:CC:DD:EE:FF", "office")
        assert sensor.name == "office"
        assert sensor.mac_address == "AA:BB:CC:DD:EE:FF"


class TestAranet4Reading:
    """Test Aranet4Reading dataclass"""

    def test_to_dict(self):
        """to_dict returns correct dictionary"""
        reading = Aranet4Reading(
            co2=800,
            temperature=22.5,
            humidity=50,
            pressure=1013.0,
            battery=90,
            interval=300,
            ago=10,
            timestamp=1234567890.0,
        )

        result = reading.to_dict()

        assert result == {
            "co2": 800,
            "temperature": 22.5,
            "humidity": 50,
            "pressure": 1013.0,
            "battery": 90,
            "interval": 300,
            "ago": 10,
        }
        # timestamp not included in to_dict
        assert "timestamp" not in result


class TestAranet4DataSource:
    """Test Aranet4DataSource class"""

    def test_init_with_device(self):
        """DataSource stores device reference"""
        config = Aranet4Config(sensors=[])
        device = Aranet4Device()
        source = Aranet4DataSource(config, device)

        assert source._device is device
        assert source._enabled is False  # no sensors configured

    def test_init_enabled_with_sensors(self):
        """DataSource is enabled with configured sensors"""
        config = Aranet4Config(
            sensors=[
                Aranet4SensorConfig(label="office", mac_address="AA:BB:CC:DD:EE:FF", enabled=True)
            ]
        )
        device = Aranet4Device()
        source = Aranet4DataSource(config, device)

        assert source._enabled is True

    @pytest.mark.asyncio
    async def test_initialize_registers_sensors_with_device(self):
        """initialize() creates sensors and registers with device"""
        config = Aranet4Config(
            sensors=[
                Aranet4SensorConfig(label="office", mac_address="AA:BB:CC:DD:EE:FF", enabled=True),
                Aranet4SensorConfig(label="bedroom", mac_address="11:22:33:44:55:66", enabled=True),
            ],
        )
        device = Aranet4Device()
        source = Aranet4DataSource(config, device)

        await source.initialize()

        assert "office" in device.sensors
        assert "bedroom" in device.sensors
        assert device.sensors["office"].mac_address == "AA:BB:CC:DD:EE:FF"
        assert device.sensors["office"].name == "office"

    @pytest.mark.asyncio
    async def test_initialize_skips_disabled_sensors(self):
        """initialize() skips disabled sensors"""
        config = Aranet4Config(
            sensors=[
                Aranet4SensorConfig(label="office", mac_address="AA:BB:CC:DD:EE:FF", enabled=True),
                Aranet4SensorConfig(
                    label="disabled", mac_address="11:22:33:44:55:66", enabled=False
                ),
            ]
        )
        device = Aranet4Device()
        source = Aranet4DataSource(config, device)

        await source.initialize()

        assert "office" in device.sensors
        assert "disabled" not in device.sensors

    @pytest.mark.asyncio
    async def test_fetch_readings_returns_empty_when_disabled(self):
        """fetch_readings() returns empty list when disabled"""
        config = Aranet4Config(sensors=[])
        device = Aranet4Device()
        source = Aranet4DataSource(config, device)

        readings = await source.fetch_readings()

        assert readings == []

    def test_get_sensor_status(self):
        """get_sensor_status() returns config info from device sensors"""
        config = Aranet4Config(sensors=[])
        device = Aranet4Device()
        sensor = Aranet4Sensor("AA:BB:CC:DD:EE:FF", "office")
        device.add_sensor("office", sensor)
        source = Aranet4DataSource(config, device)

        status = source.get_sensor_status()

        assert "office" in status
        assert status["office"]["name"] == "office"
        assert status["office"]["mac_address"] == "AA:BB:CC:DD:EE:FF"

    @pytest.mark.asyncio
    async def test_health_check_with_sensors(self):
        """health_check returns True when enabled with sensors"""
        config = Aranet4Config(
            sensors=[
                Aranet4SensorConfig(label="office", mac_address="AA:BB:CC:DD:EE:FF", enabled=True)
            ]
        )
        device = Aranet4Device()
        source = Aranet4DataSource(config, device)
        await source.initialize()

        assert await source.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_without_sensors(self):
        """health_check returns False when no sensors"""
        config = Aranet4Config(sensors=[])
        device = Aranet4Device()
        source = Aranet4DataSource(config, device)

        assert await source.health_check() is False
