"""Aranet4 CO2 sensor data source implementation"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from ..config import Aranet4Config
from .base import DataSource, DataSourceMetadata, SensorReading

if TYPE_CHECKING:
    from ..aranet4 import Aranet4Sensor

logger = logging.getLogger(__name__)


class Aranet4DataSource(DataSource):
    """
    Aranet4 BLE CO2 sensors data source.

    Note: BLE scans are expensive and slow, so this data source maintains
    a background polling task. fetch_readings() returns the latest data
    from the background poller, not a fresh BLE scan.
    """

    def __init__(self, config: Aranet4Config):
        """
        Initialize Aranet4 data source.

        Args:
            config: Aranet4 configuration
        """
        self._config = config
        self._sensors: dict[str, Aranet4Sensor] = {}  # label -> sensor
        self._enabled = len([s for s in config.sensors if s.enabled]) > 0

    async def initialize(self) -> None:
        """
        Start background BLE polling for configured sensors.

        This registers each enabled sensor and starts the global polling task.
        """
        if not self._enabled:
            logger.info("No Aranet4 sensors enabled, skipping initialization")
            return

        try:
            # Import aranet4 module functions
            from ..aranet4 import Aranet4Sensor, register_sensor

            # Register each enabled sensor
            for sensor_config in self._config.sensors:
                if sensor_config.enabled and sensor_config.mac_address:
                    sensor = Aranet4Sensor(
                        mac_address=sensor_config.mac_address,
                        name=sensor_config.label or sensor_config.mac_address[-8:],
                        cache_duration=self._config.cache_duration,
                    )
                    self._sensors[sensor_config.label] = sensor
                    register_sensor(sensor)
                    logger.info(
                        f"Registered Aranet4 sensor: {sensor_config.label} "
                        f"({sensor_config.mac_address})"
                    )

            logger.info(f"Aranet4 data source initialized with {len(self._sensors)} sensor(s)")

        except ImportError:
            logger.error("aranet4 package not installed, cannot initialize sensors")
            self._enabled = False
        except Exception as e:
            logger.error(f"Error initializing Aranet4 data source: {e}")
            self._enabled = False

    async def fetch_readings(self) -> list[SensorReading]:
        """
        Return latest data from background BLE poller.

        This doesn't trigger a new BLE scan (too expensive), but returns
        the most recent reading from the continuous polling task.

        Returns:
            List of sensor readings from all configured sensors.
            Each reading represents one sensor with a nested dict value
            containing temperature, co2, humidity, pressure, and battery.
        """
        if not self._enabled:
            return []

        readings = []

        try:
            for label, sensor in self._sensors.items():
                reading = sensor.get_cached_reading()
                if reading:
                    # Create a single reading per sensor with nested dict value
                    # This matches the format expected by the controller
                    readings.append(
                        SensorReading(
                            sensor_id=label,
                            value={
                                "temperature": reading.temperature,
                                "co2": reading.co2,
                                "humidity": reading.humidity,
                                "pressure": reading.pressure,
                                "battery": reading.battery,
                            },
                            unit=None,
                            timestamp=datetime.fromtimestamp(reading.timestamp),
                        )
                    )

        except Exception as e:
            logger.error(f"Error fetching Aranet4 readings: {e}")

        return readings

    def get_metadata(self) -> DataSourceMetadata:
        """Get Aranet4 data source metadata"""
        sensor_count = len(self._sensors)
        sensor_list = ", ".join(self._sensors.keys()) if self._sensors else "none"

        return DataSourceMetadata(
            source_id="co2",
            name="Aranet4 CO2 Sensors",
            description=f"BLE CO2 sensors: {sensor_list} ({sensor_count} configured)",
            refresh_interval=30,
            requires_auth=False,
            enabled=self._enabled,
        )

    async def health_check(self) -> bool:
        """Check if any sensor has recent data"""
        if not self._enabled:
            return False

        # Check if at least one sensor has a recent reading
        return any(s.get_cached_reading() for s in self._sensors.values())

    async def shutdown(self) -> None:
        """Stop background BLE polling"""
        try:
            from ..aranet4 import stop_polling, unregister_sensor

            # Unregister all sensors
            for label, sensor in list(self._sensors.items()):
                unregister_sensor(sensor)
                logger.debug(f"Unregistered Aranet4 sensor: {label}")

            # Stop the global polling task
            await stop_polling()
            logger.info("Aranet4 data source shut down")

        except Exception as e:
            logger.error(f"Error shutting down Aranet4 data source: {e}")
