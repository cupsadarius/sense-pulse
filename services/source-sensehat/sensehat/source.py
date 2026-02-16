"""Sense HAT sensor polling source."""

from __future__ import annotations

import asyncio
import logging
import time

from sense_common.models import SensorReading

logger = logging.getLogger(__name__)


class SenseHatSensorSource:
    """Reads temperature, humidity, and pressure from Sense HAT hardware."""

    def __init__(self):
        self._sense_hat = None
        self._available = False

    async def initialize(self) -> None:
        """Initialize Sense HAT hardware (lazy, graceful if unavailable)."""
        try:
            from sense_hat import SenseHat

            self._sense_hat = await asyncio.to_thread(SenseHat)
            self._available = True
            logger.info("Sense HAT sensor source initialized")
        except ImportError:
            logger.warning("sense_hat module not installed -- sensor source unavailable")
            self._available = False
        except Exception as e:
            logger.warning("Sense HAT hardware not available: %s", e)
            self._available = False

    def _read_sync(self) -> dict[str, float | None]:
        """Synchronous sensor read (runs in thread pool)."""
        if not self._available or self._sense_hat is None:
            return {"temperature": None, "humidity": None, "pressure": None}
        try:
            return {
                "temperature": round(self._sense_hat.get_temperature(), 1),
                "humidity": round(self._sense_hat.get_humidity(), 1),
                "pressure": round(self._sense_hat.get_pressure(), 1),
            }
        except Exception as e:
            logger.error("Failed to read sensors: %s", e)
            return {"temperature": None, "humidity": None, "pressure": None}

    async def poll(self) -> list[SensorReading]:
        """Poll sensors and return readings."""
        if not self._available:
            return []

        data = await asyncio.to_thread(self._read_sync)
        now = time.time()
        readings: list[SensorReading] = []

        if data["temperature"] is not None:
            readings.append(
                SensorReading(
                    sensor_id="temperature", value=data["temperature"], unit="C", timestamp=now
                )
            )
        if data["humidity"] is not None:
            readings.append(
                SensorReading(sensor_id="humidity", value=data["humidity"], unit="%", timestamp=now)
            )
        if data["pressure"] is not None:
            readings.append(
                SensorReading(
                    sensor_id="pressure", value=data["pressure"], unit="mbar", timestamp=now
                )
            )

        return readings

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def sense_hat(self):
        return self._sense_hat
