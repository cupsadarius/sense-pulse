"""Aranet4 CO2 sensor data source implementation"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..config import Aranet4Config
from ..web.log_handler import get_structured_logger
from .base import DataSource, DataSourceMetadata, SensorReading

if TYPE_CHECKING:
    from ..devices.aranet4 import Aranet4Device

logger = get_structured_logger(__name__, component="aranet4")


class Aranet4DataSource(DataSource):
    """
    Aranet4 BLE CO2 sensors data source.

    Uses BLE scanning to read sensor data from advertisements.
    This is more reliable than direct connections.
    See: https://github.com/hbldh/bleak/issues/1475

    No internal caching - relies on DataCache's caching mechanism.
    """

    def __init__(self, config: Aranet4Config, device: Aranet4Device):
        self._config = config
        self._device = device
        self._enabled = len([s for s in config.sensors if s.enabled]) > 0

    async def initialize(self) -> None:
        """Initialize sensor instances and register with device."""
        if not self._enabled:
            logger.info("No Aranet4 sensors enabled, skipping initialization")
            return

        try:
            from ..devices.aranet4 import Aranet4Sensor

            for sensor_config in self._config.sensors:
                if sensor_config.enabled and sensor_config.mac_address:
                    sensor = Aranet4Sensor(
                        mac_address=sensor_config.mac_address,
                        name=sensor_config.label or sensor_config.mac_address[-8:],
                    )
                    self._device.add_sensor(sensor_config.label, sensor)
                    logger.info(
                        "Registered Aranet4 sensor",
                        label=sensor_config.label,
                        mac_address=sensor_config.mac_address,
                    )

            logger.info(
                "Aranet4 data source initialized",
                sensor_count=len(self._device.sensors),
            )

        except ImportError:
            logger.error("aranet4 package not installed")
            self._enabled = False
        except Exception as e:
            logger.error("Error initializing Aranet4", error=str(e))
            self._enabled = False

    async def fetch_readings(self) -> list[SensorReading]:
        """Fetch readings via BLE scan."""
        if not self._enabled or not self._device.sensors:
            return []

        readings = []
        logger.info("Fetching Aranet4 readings", sensor_count=len(self._device.sensors))

        # Device handles lock coordination and BLE scanning
        results = await self._device.read_all_sensors()

        for label, reading_data in results.items():
            if reading_data:
                readings.append(
                    SensorReading(
                        sensor_id=label,
                        value={
                            "temperature": reading_data.temperature,
                            "co2": reading_data.co2,
                            "humidity": reading_data.humidity,
                            "pressure": reading_data.pressure,
                            "battery": reading_data.battery,
                        },
                        unit=None,
                        timestamp=datetime.fromtimestamp(reading_data.timestamp),
                    )
                )

        logger.info("Aranet4 fetch completed", readings_count=len(readings))
        return readings

    def get_metadata(self) -> DataSourceMetadata:
        """Get Aranet4 data source metadata"""
        sensor_count = len(self._device.sensors)
        sensor_list = ", ".join(self._device.sensors.keys()) if self._device.sensors else "none"

        return DataSourceMetadata(
            source_id="co2",
            name="Aranet4 CO2 Sensors",
            description=f"BLE CO2 sensors: {sensor_list} ({sensor_count} configured)",
            refresh_interval=30,
            requires_auth=False,
            enabled=self._enabled,
        )

    async def health_check(self) -> bool:
        """Check if Aranet4 source is configured with sensors."""
        return self._enabled and len(self._device.sensors) > 0

    def get_sensor_status(self) -> dict[str, dict[str, Any]]:
        """Get config info for all sensors (for web UI).

        Returns sensor configuration. Actual readings come from DataCache.
        """
        return {
            label: {
                "name": sensor.name,
                "mac_address": sensor.mac_address,
            }
            for label, sensor in self._device.sensors.items()
        }

    async def shutdown(self) -> None:
        """Clean up resources"""
        logger.info("Aranet4 data source shut down")
