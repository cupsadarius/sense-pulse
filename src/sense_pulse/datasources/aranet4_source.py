"""Aranet4 CO2 sensor data source implementation"""

from __future__ import annotations

import asyncio
import contextlib
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
        self._polling_task: asyncio.Task | None = None
        self._polling_stop_event = asyncio.Event()
        self._poll_interval = 30  # seconds
        self._scan_duration = 8  # seconds for BLE scan
        self._task_counter = 0

    async def initialize(self) -> None:
        """
        Start background BLE polling for configured sensors.

        This registers each enabled sensor and starts the polling task.
        """
        if not self._enabled:
            logger.info("No Aranet4 sensors enabled, skipping initialization")
            return

        try:
            # Import aranet4 module functions
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

            # Start background polling task
            await self._start_polling()

        except ImportError:
            logger.error("aranet4 package not installed, cannot initialize sensors")
            self._enabled = False
        except Exception as e:
            logger.error(f"Error initializing Aranet4 data source: {e}")
            self._enabled = False

    async def _start_polling(self) -> None:
        """Start the background polling task"""
        if self._polling_task is not None and not self._polling_task.done():
            logger.warning("Aranet4 polling task already running")
            return

        self._polling_stop_event.clear()
        self._polling_task = asyncio.create_task(self._polling_loop())
        logger.info("Aranet4 background polling task started")

    async def _polling_loop(self) -> None:
        """Background task that scans for all sensors at once"""
        self._task_counter += 1
        task_id = self._task_counter
        logger.info(f"Aranet4 background polling started (task #{task_id})")

        while not self._polling_stop_event.is_set():
            try:
                # Import scan utilities
                from ..devices.aranet4 import do_ble_scan, get_scan_lock

                # Single scan gets all devices (run in thread pool to avoid blocking)
                logger.debug(f"Aranet4 task #{task_id}: Waiting for scan lock...")

                def locked_scan():
                    """Run scan with lock held"""
                    with get_scan_lock():
                        logger.debug(f"Aranet4 task #{task_id}: Acquired scan lock, starting scan")
                        return do_ble_scan(scan_duration=self._scan_duration)

                readings = await asyncio.to_thread(locked_scan)

                # Update each registered sensor with its reading
                for label, sensor in self._sensors.items():
                    if sensor.mac_address in readings:
                        sensor.update_reading(readings[sensor.mac_address])
                    else:
                        sensor.set_error("Not found in scan")

            except Exception as e:
                logger.error(f"Aranet4 polling error (task #{task_id}): {e}")

            # Wait for next poll interval
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    self._polling_stop_event.wait(), timeout=self._poll_interval
                )

        logger.info(f"Aranet4 background polling stopped (task #{task_id})")

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

    def get_sensor_status(self) -> dict[str, dict]:
        """Get status of all sensors (for web UI)"""
        return {label: sensor.get_status() for label, sensor in self._sensors.items()}

    async def shutdown(self) -> None:
        """Stop background BLE polling"""
        try:
            logger.info("Stopping Aranet4 data source...")

            # Stop the polling task
            if self._polling_task and not self._polling_task.done():
                self._polling_stop_event.set()

                try:
                    await asyncio.wait_for(self._polling_task, timeout=5.0)
                    logger.info("Aranet4 polling task stopped")
                except asyncio.TimeoutError:
                    logger.warning("Polling task did not stop gracefully, cancelling")
                    self._polling_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self._polling_task

            # Clear sensors
            for label in list(self._sensors.keys()):
                logger.debug(f"Unregistered Aranet4 sensor: {label}")
            self._sensors.clear()

            logger.info("Aranet4 data source shut down")

        except Exception as e:
            logger.error(f"Error shutting down Aranet4 data source: {e}")
