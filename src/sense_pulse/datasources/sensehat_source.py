"""Sense HAT onboard sensors data source implementation"""

import logging
from datetime import datetime

from ..devices.sensehat import get_sensor_data
from .base import DataSource, DataSourceMetadata, SensorReading

logger = logging.getLogger(__name__)


class SenseHatDataSource(DataSource):
    """
    Sense HAT onboard sensors data source.

    Reads temperature, humidity, and pressure from the Sense HAT hardware.
    Gracefully handles hardware not being available.
    """

    def __init__(self):
        """Initialize Sense HAT data source"""
        self._available = True

    async def initialize(self) -> None:
        """Initialize Sense HAT data source"""
        # Test if hardware is available
        data = await get_sensor_data()
        self._available = data.get("available", False)

        if self._available:
            logger.info("Sense HAT data source initialized successfully")
        else:
            logger.warning("Sense HAT hardware not available")

    async def fetch_readings(self) -> list[SensorReading]:
        """
        Fetch fresh readings from Sense HAT sensors.

        Returns:
            List of sensor readings (temperature, humidity, pressure)
        """
        try:
            data = await get_sensor_data()
            now = datetime.now()

            # Only return readings if hardware is available
            if not data.get("available", False):
                logger.debug("Sense HAT hardware not available, returning empty readings")
                return []

            readings = []

            # Add readings only for non-None values
            if data.get("temperature") is not None:
                readings.append(
                    SensorReading(
                        sensor_id="temperature",
                        value=data["temperature"],
                        unit="°C",
                        timestamp=now,
                    )
                )

            if data.get("humidity") is not None:
                readings.append(
                    SensorReading(
                        sensor_id="humidity",
                        value=data["humidity"],
                        unit="%",
                        timestamp=now,
                    )
                )

            if data.get("pressure") is not None:
                readings.append(
                    SensorReading(
                        sensor_id="pressure",
                        value=data["pressure"],
                        unit="mbar",
                        timestamp=now,
                    )
                )

            return readings

        except Exception as e:
            logger.error(f"Error fetching Sense HAT readings: {e}")
            return []

    def get_metadata(self) -> DataSourceMetadata:
        """Get Sense HAT data source metadata"""
        return DataSourceMetadata(
            source_id="sensors",
            name="Sense HAT Sensors",
            description="Onboard temperature, humidity, and pressure sensors",
            refresh_interval=30,
            requires_auth=False,
            enabled=self._available,
        )

    async def health_check(self) -> bool:
        """Check if Sense HAT hardware is available"""
        try:
            data = await get_sensor_data()
            return data.get("available", False)
        except Exception as e:
            logger.debug(f"Sense HAT health check failed: {e}")
            return False

    async def shutdown(self) -> None:
        """Clean up resources (no-op for Sense HAT)"""
        logger.debug("Sense HAT data source shut down")
