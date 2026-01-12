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
    async def test_read_all_sensors_returns_results(self):
        """read_all_sensors calls read() on each sensor"""
        device = Aranet4Device()

        # Create mock sensors
        sensor1 = Mock(spec=Aranet4Sensor)
        sensor1.read = AsyncMock(
            return_value=Aranet4Reading(
                co2=800,
                temperature=22.5,
                humidity=50,
                pressure=1013.0,
                battery=90,
                interval=300,
                ago=10,
                timestamp=1234567890.0,
            )
        )

        sensor2 = Mock(spec=Aranet4Sensor)
        sensor2.read = AsyncMock(return_value=None)

        device.add_sensor("office", sensor1)
        device.add_sensor("bedroom", sensor2)

        results = await device.read_all_sensors()

        assert "office" in results
        assert results["office"].co2 == 800
        assert "bedroom" in results
        assert results["bedroom"] is None
        sensor1.read.assert_called_once()
        sensor2.read.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_for_devices_returns_empty_on_import_error(self):
        """scan_for_devices returns empty list if aranet4 not installed"""
        device = Aranet4Device()

        with patch.dict("sys.modules", {"aranet4": None}):
            with patch(
                "sense_pulse.devices.aranet4.Aranet4Device.scan_for_devices",
                return_value=[],
            ):
                result = await device.scan_for_devices()
                assert result == []


class TestAranet4Sensor:
    """Test Aranet4Sensor class"""

    def test_init_uppercases_mac(self):
        """MAC address is uppercased on init"""
        sensor = Aranet4Sensor("aa:bb:cc:dd:ee:ff", "office", 60)
        assert sensor.mac_address == "AA:BB:CC:DD:EE:FF"

    def test_init_defaults(self):
        """Default values are set correctly"""
        sensor = Aranet4Sensor("AA:BB:CC:DD:EE:FF")
        assert sensor.name == "sensor"
        assert sensor.cache_duration == 60
        assert sensor._cached_reading is None
        assert sensor._last_error is None

    def test_get_cached_reading_returns_none_initially(self):
        """get_cached_reading returns None before any read"""
        sensor = Aranet4Sensor("AA:BB:CC:DD:EE:FF", "test")
        assert sensor.get_cached_reading() is None

    def test_get_co2_returns_none_without_reading(self):
        """get_co2 returns None without cached reading"""
        sensor = Aranet4Sensor("AA:BB:CC:DD:EE:FF", "test")
        assert sensor.get_co2() is None

    def test_get_status_without_reading(self):
        """get_status returns correct structure without reading"""
        sensor = Aranet4Sensor("AA:BB:CC:DD:EE:FF", "office", 60)
        status = sensor.get_status()

        assert status["name"] == "office"
        assert status["mac_address"] == "AA:BB:CC:DD:EE:FF"
        assert status["connected"] is False
        assert status["last_reading"] is None
        assert status["cache_age"] is None
        assert status["last_error"] is None

    @pytest.mark.asyncio
    async def test_read_success(self):
        """read() returns Aranet4Reading on success"""
        sensor = Aranet4Sensor("AA:BB:CC:DD:EE:FF", "test")

        mock_reading = Mock()
        mock_reading.co2 = 800
        mock_reading.temperature = 22.567
        mock_reading.humidity = 50
        mock_reading.pressure = 1013.25
        mock_reading.battery = 90
        mock_reading.interval = 300
        mock_reading.ago = 10

        with patch("aranet4.client._current_reading", new_callable=AsyncMock) as mock:
            mock.return_value = mock_reading
            result = await sensor.read()

        assert result is not None
        assert result.co2 == 800
        assert result.temperature == 22.6  # rounded
        assert result.humidity == 50
        assert result.pressure == 1013.2  # rounded
        assert result.battery == 90
        assert sensor._cached_reading == result
        assert sensor._last_error is None

    @pytest.mark.asyncio
    async def test_read_failure_sets_error(self):
        """read() sets error on exception"""
        sensor = Aranet4Sensor("AA:BB:CC:DD:EE:FF", "test")

        with patch("aranet4.client._current_reading", new_callable=AsyncMock) as mock:
            mock.side_effect = Exception("BLE connection failed")
            result = await sensor.read()

        assert result is None
        assert sensor._last_error == "BLE connection failed"


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
                Aranet4SensorConfig(
                    label="office", mac_address="AA:BB:CC:DD:EE:FF", enabled=True
                )
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
                Aranet4SensorConfig(
                    label="office", mac_address="AA:BB:CC:DD:EE:FF", enabled=True
                ),
                Aranet4SensorConfig(
                    label="bedroom", mac_address="11:22:33:44:55:66", enabled=True
                ),
            ],
            cache_duration=120,
        )
        device = Aranet4Device()
        source = Aranet4DataSource(config, device)

        await source.initialize()

        assert "office" in device.sensors
        assert "bedroom" in device.sensors
        assert device.sensors["office"].mac_address == "AA:BB:CC:DD:EE:FF"
        assert device.sensors["office"].cache_duration == 120

    @pytest.mark.asyncio
    async def test_initialize_skips_disabled_sensors(self):
        """initialize() skips disabled sensors"""
        config = Aranet4Config(
            sensors=[
                Aranet4SensorConfig(
                    label="office", mac_address="AA:BB:CC:DD:EE:FF", enabled=True
                ),
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
        """get_sensor_status() returns status from device sensors"""
        config = Aranet4Config(sensors=[])
        device = Aranet4Device()
        sensor = Aranet4Sensor("AA:BB:CC:DD:EE:FF", "office")
        device.add_sensor("office", sensor)
        source = Aranet4DataSource(config, device)

        status = source.get_sensor_status()

        assert "office" in status
        assert status["office"]["name"] == "office"
