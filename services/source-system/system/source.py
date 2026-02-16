"""System metrics data source using psutil."""

from __future__ import annotations

import asyncio
import logging
import os

import psutil  # type: ignore[import-untyped]
import redis.asyncio as aioredis

from sense_common.ephemeral import EphemeralSource
from sense_common.models import SensorReading, SourceMetadata

logger = logging.getLogger(__name__)


class SystemSource(EphemeralSource):
    """Ephemeral source that collects system metrics via psutil."""

    @property
    def source_id(self) -> str:
        return "system"

    @property
    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            source_id="system",
            name="System Stats",
            description="CPU, memory, load, and temperature metrics",
            refresh_interval=30,
        )

    async def poll(self, redis: aioredis.Redis) -> list[SensorReading]:
        """Collect system metrics and return 4 readings."""
        # Support containerized mode: psutil reads from /host/proc if mounted
        if os.path.isdir("/host/proc"):
            os.environ["HOST_PROC"] = "/host/proc"

        stats = await asyncio.to_thread(self._collect_stats)

        return [
            SensorReading(
                sensor_id="cpu_percent",
                value=stats["cpu_percent"],
                unit="%",
            ),
            SensorReading(
                sensor_id="memory_percent",
                value=stats["memory_percent"],
                unit="%",
            ),
            SensorReading(
                sensor_id="load_1min",
                value=stats["load_1min"],
                unit="load",
            ),
            SensorReading(
                sensor_id="cpu_temp",
                value=stats["cpu_temp"],
                unit="C",
            ),
        ]

    @staticmethod
    def _collect_stats() -> dict[str, float]:
        """Collect system stats synchronously (run in thread)."""
        try:
            cpu = psutil.cpu_percent(interval=1)
        except Exception:
            cpu = 0.0

        try:
            memory = psutil.virtual_memory().percent
        except Exception:
            memory = 0.0

        try:
            load = os.getloadavg()[0]
        except (OSError, AttributeError):
            load = 0.0

        cpu_temp = 0.0
        try:
            temps = psutil.sensors_temperatures()
            if "cpu_thermal" in temps and temps["cpu_thermal"]:
                cpu_temp = temps["cpu_thermal"][0].current
            elif "coretemp" in temps and temps["coretemp"]:
                cpu_temp = temps["coretemp"][0].current
        except (AttributeError, KeyError, IndexError, OSError):
            pass

        return {
            "cpu_percent": round(cpu, 1),
            "memory_percent": round(memory, 1),
            "load_1min": round(load, 2),
            "cpu_temp": round(cpu_temp, 1),
        }
