"""Aranet4 CO2 sensor data source implementation"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from ..config import Aranet4Config
from .base import DataSource, DataSourceMetadata, SensorReading

if TYPE_CHECKING:
    from ..devices.aranet4 import Aranet4Sensor

logger = logging.getLogger(__name__)


class Aranet4DataSource(DataSource):
    """
    Aranet4 BLE CO2 sensors data source.

    Performs a BLE scan when fetch_readings() is called.
    No internal polling - relies on Cache's polling mechanism.
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
        self._scan_duration = 8  # seconds for BLE scan

    async def initialize(self) -> None:
        """
        Initialize sensor instances.

        Creates Aranet4Sensor objects for each configured sensor.
        Does NOT start any background polling - Cache handles that.
        """
        if not self._enabled:
            logger.info("No Aranet4 sensors enabled, skipping initialization")
            return

        try:
            # Import aranet4 module
            from ..devices.aranet4 import Aranet4Sensor

            # Create sensor instances for each enabled sensor
            for sensor_config in self._config.sensors:
                if sensor_config.enabled and sensor_config.mac_address:
                    sensor = Aranet4Sensor(
                        mac_address=sensor_config.mac_address,
                        name=sensor_config.label or sensor_config.mac_address[-8:],
                        cache_duration=self._config.cache_duration,
                    )
                    self._sensors[sensor_config.label] = sensor
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
        Fetch fresh readings by performing a BLE scan.

        This triggers a single BLE scan to read all configured sensors.
        The scan takes ~8 seconds. Results are cached in sensor instances.

        Returns:
            List of sensor readings from all configured sensors.
            Each reading represents one sensor with a nested dict value
            containing temperature, co2, humidity, pressure, and battery.
        """
        if not self._enabled or not self._sensors:
            return []

        readings = []

        try:
            # Import scan utilities
            from ..devices.aranet4 import do_ble_scan, get_scan_lock

            # Perform a single BLE scan for all sensors
            logger.debug("Aranet4: Starting BLE scan...")

            def locked_scan():
                """Run scan with lock held"""
                with get_scan_lock():
                    return do_ble_scan(scan_duration=self._scan_duration)

            # Run scan in thread pool (blocking operation)
            scan_results = await asyncio.to_thread(locked_scan)

            # Update each sensor with its reading from the scan
            for label, sensor in self._sensors.items():
                if sensor.mac_address in scan_results:
                    reading_data = scan_results[sensor.mac_address]
                    sensor.update_reading(reading_data)

                    # Create sensor reading for cache
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
                else:
                    sensor.set_error("Not found in scan")
                    logger.warning(f"Sensor {label} ({sensor.mac_address}) not found in BLE scan")

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

        # Check if at least one sensor has a cached reading
        return any(s.get_cached_reading() for s in self._sensors.values())

    def get_sensor_status(self) -> dict[str, dict]:
        """Get status of all sensors (for web UI)"""
        return {label: sensor.get_status() for label, sensor in self._sensors.items()}

    async def shutdown(self) -> None:
        """Clean up resources"""
        try:
            logger.info("Stopping Aranet4 data source...")

            # Clear sensors
            for label in list(self._sensors.keys()):
                logger.debug(f"Unregistered Aranet4 sensor: {label}")
            self._sensors.clear()

            logger.info("Aranet4 data source shut down")

        except Exception as e:
            logger.error(f"Error shutting down Aranet4 data source: {e}")
