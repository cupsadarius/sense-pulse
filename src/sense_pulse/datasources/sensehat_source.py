"""Sense HAT onboard sensors data source implementation"""

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from ..devices.sensehat_sensors import SenseHatSensors
from ..web.log_handler import get_structured_logger
from .base import DataSource, DataSourceMetadata, SensorReading

if TYPE_CHECKING:
    from sense_hat import SenseHat

logger = get_structured_logger(__name__, component="sensehat")


class SenseHatDataSource(DataSource):
    """
    Sense HAT onboard sensors data source.

    Reads temperature, humidity, and pressure from the Sense HAT hardware.
    Gracefully handles hardware not being available.

    This DataSource owns the Sense HAT hardware instance and delegates
    sensor reading to SenseHatSensors.
    """

    def __init__(self):
        """Initialize Sense HAT data source"""
        self._sense_hat: Optional[SenseHat] = None
        self._sensors: Optional[SenseHatSensors] = None
        self._available = False

    async def initialize(self) -> None:
        """Initialize Sense HAT hardware"""
        try:
            from sense_hat import SenseHat

            # Initialize hardware in thread pool (blocking operation)
            self._sense_hat = await asyncio.to_thread(SenseHat)
            # Create sensors wrapper with the shared instance
            self._sensors = SenseHatSensors(self._sense_hat)
            self._available = True
            logger.info("Sense HAT data source initialized")

        except ImportError:
            logger.warning("Sense HAT module not installed", available=False)
            self._available = False
        except Exception as e:
            logger.warning("Sense HAT hardware not available", error=str(e))
            self._available = False

    async def fetch_readings(self) -> list[SensorReading]:
        """
        Fetch fresh readings from Sense HAT sensors.

        Returns:
            List of sensor readings (temperature, humidity, pressure)
        """
        if not self._available or self._sensors is None:
            return []

        try:
            # Read sensors using the sensors wrapper
            data = await self._sensors.get_all()
            now = datetime.now()
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
            logger.error("Error fetching Sense HAT readings", error=str(e))
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
        """Check if Sense HAT hardware is available and responsive"""
        if not self._available or self._sensors is None:
            return False

        try:
            # Try a quick read to verify hardware is working
            data = await self._sensors.get_all()
            return any(v is not None for k, v in data.items() if k != "available")
        except Exception as e:
            logger.debug("Sense HAT health check failed", error=str(e))
            return False

    def is_available(self) -> bool:
        """Check if Sense HAT hardware is available"""
        return self._available

    def get_sense_hat_instance(self) -> Optional["SenseHat"]:
        """Get the Sense HAT hardware instance (for display/LED access)"""
        return self._sense_hat

    async def shutdown(self) -> None:
        """Clean up resources"""
        self._sense_hat = None
        self._sensors = None
        self._available = False
        logger.debug("Sense HAT data source shut down")
