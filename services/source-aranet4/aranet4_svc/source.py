"""Aranet4 ephemeral data source.

Reads configured sensors via BLE scan and returns 5 scalar readings per sensor.
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

from sense_common.config import get_config_value
from sense_common.ephemeral import EphemeralSource
from sense_common.models import SensorReading, SourceMetadata
from sense_common.redis_client import read_config

from aranet4_svc.scanner import Aranet4Scanner

logger = logging.getLogger(__name__)


class Aranet4Source(EphemeralSource):
    """Ephemeral source that reads Aranet4 BLE CO2 sensors."""

    @property
    def source_id(self) -> str:
        return "co2"

    @property
    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            source_id="co2",
            name="Aranet4 CO2 Sensors",
            description="BLE CO2 sensors via passive scanning",
            refresh_interval=60,
        )

    async def poll(self, redis: aioredis.Redis) -> list[SensorReading]:
        """Poll configured Aranet4 sensors and return scalar readings.

        For each sensor found, produces 5 readings:
        - {label}:co2 (int, ppm)
        - {label}:temperature (float, C)
        - {label}:humidity (int, %)
        - {label}:pressure (float, mbar)
        - {label}:battery (int, %)
        """
        config = await read_config(redis, "aranet4")
        sensors: list[dict] = get_config_value(config, "ARANET4_SENSORS", default=[])
        timeout: int = get_config_value(config, "ARANET4_TIMEOUT", default=10)

        if not sensors:
            logger.warning("No Aranet4 sensors configured")
            return []

        scanner = Aranet4Scanner()
        results = await scanner.scan(sensors, timeout=timeout)

        readings: list[SensorReading] = []
        for label, reading in results.items():
            if reading is None:
                logger.warning("Sensor '%s' not found in scan", label)
                continue

            ts = reading.timestamp
            readings.extend(
                [
                    SensorReading(
                        sensor_id=f"{label}:co2",
                        value=reading.co2,
                        unit="ppm",
                        timestamp=ts,
                    ),
                    SensorReading(
                        sensor_id=f"{label}:temperature",
                        value=reading.temperature,
                        unit="C",
                        timestamp=ts,
                    ),
                    SensorReading(
                        sensor_id=f"{label}:humidity",
                        value=reading.humidity,
                        unit="%",
                        timestamp=ts,
                    ),
                    SensorReading(
                        sensor_id=f"{label}:pressure",
                        value=reading.pressure,
                        unit="mbar",
                        timestamp=ts,
                    ),
                    SensorReading(
                        sensor_id=f"{label}:battery",
                        value=reading.battery,
                        unit="%",
                        timestamp=ts,
                    ),
                ]
            )

        logger.info("Aranet4 poll: %d readings from %d sensors", len(readings), len(results))
        return readings
