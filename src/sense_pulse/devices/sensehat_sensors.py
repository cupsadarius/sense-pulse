"""Read-only access to SenseHat environmental sensors.

This module provides sensor reading functionality from the SenseHat hardware.
It can work with a shared SenseHat instance (recommended) or create its own.

Usage:
    # With shared instance (recommended)
    from sense_hat import SenseHat
    sense_hat = SenseHat()
    sensors = SenseHatSensors(sense_hat)
    data = sensors.get_all()

    # With lazy initialization (fallback)
    sensors = SenseHatSensors()
    if sensors.available:
        data = sensors.get_all()
"""

import asyncio
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from sense_hat import SenseHat

from ..web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="sensehat.sensors")


class SenseHatSensors:
    """
    Manages sensor readings from SenseHat hardware.

    This class provides read-only access to the SenseHat's environmental sensors
    (temperature, humidity, pressure). It can use a provided SenseHat instance
    or lazily initialize its own.

    Attributes:
        available: Whether the SenseHat hardware is available for sensor readings
    """

    def __init__(self, sense_hat: Optional["SenseHat"] = None):
        """
        Initialize SenseHat sensors.

        Args:
            sense_hat: Optional SenseHat instance to use. If not provided,
                      will attempt lazy initialization when first accessed.
        """
        self._sense_hat: Optional[SenseHat] = sense_hat
        self._available: Optional[bool] = None if sense_hat is None else True
        self._initialized: bool = sense_hat is not None

        if sense_hat is not None:
            logger.debug("SenseHatSensors initialized with provided instance")

    def _ensure_initialized(self) -> bool:
        """Lazy initialization of SenseHat if not provided."""
        if self._initialized:
            return self._available or False

        self._initialized = True

        try:
            from sense_hat import SenseHat

            self._sense_hat = SenseHat()
            self._available = True
            logger.info("SenseHat sensors initialized via lazy initialization")
        except ImportError:
            logger.warning("SenseHat module not installed", available=False)
            self._available = False
        except Exception as e:
            logger.warning("SenseHat hardware not available", error=str(e))
            self._available = False

        return self._available or False

    @property
    def available(self) -> bool:
        """Check if SenseHat sensors are available."""
        return self._ensure_initialized()

    @property
    def sense_hat(self) -> Optional["SenseHat"]:
        """Get the underlying SenseHat instance."""
        self._ensure_initialized()
        return self._sense_hat

    def get_temperature(self) -> Optional[float]:
        """
        Get temperature reading from SenseHat.

        Returns:
            Temperature in Celsius, rounded to 1 decimal place, or None if unavailable.
        """
        if not self.available or self._sense_hat is None:
            return None
        try:
            return float(round(self._sense_hat.get_temperature(), 1))
        except Exception as e:
            logger.error("Failed to read temperature", error=str(e))
            return None

    def get_humidity(self) -> Optional[float]:
        """
        Get humidity reading from SenseHat.

        Returns:
            Relative humidity percentage, rounded to 1 decimal place, or None if unavailable.
        """
        if not self.available or self._sense_hat is None:
            return None
        try:
            return float(round(self._sense_hat.get_humidity(), 1))
        except Exception as e:
            logger.error("Failed to read humidity", error=str(e))
            return None

    def get_pressure(self) -> Optional[float]:
        """
        Get pressure reading from SenseHat.

        Returns:
            Atmospheric pressure in millibars, rounded to 1 decimal place, or None if unavailable.
        """
        if not self.available or self._sense_hat is None:
            return None
        try:
            return float(round(self._sense_hat.get_pressure(), 1))
        except Exception as e:
            logger.error("Failed to read pressure", error=str(e))
            return None

    def get_all_sync(self) -> dict[str, Any]:
        """
        Get all sensor readings synchronously.

        Returns:
            Dictionary with temperature, humidity, pressure, and availability status.
        """
        if not self.available or self._sense_hat is None:
            return {
                "temperature": None,
                "humidity": None,
                "pressure": None,
                "available": False,
            }

        try:
            data = {
                "temperature": round(self._sense_hat.get_temperature(), 1),
                "humidity": round(self._sense_hat.get_humidity(), 1),
                "pressure": round(self._sense_hat.get_pressure(), 1),
                "available": True,
            }
            logger.debug(
                "Sensor data read",
                temperature=data["temperature"],
                humidity=data["humidity"],
                pressure=data["pressure"],
            )
            return data
        except Exception as e:
            logger.error("Failed to read sensors", error=str(e))
            return {
                "temperature": None,
                "humidity": None,
                "pressure": None,
                "available": False,
                "error": str(e),
            }

    async def get_all(self) -> dict[str, Any]:
        """
        Get all sensor readings asynchronously.

        Runs the blocking sensor read in a thread pool to prevent blocking the event loop.

        Returns:
            Dictionary with temperature, humidity, pressure, and availability status.
        """
        return await asyncio.to_thread(self.get_all_sync)
