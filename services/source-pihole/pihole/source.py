"""Pi-hole data source."""

from __future__ import annotations

import logging

import httpx
from sense_common.config import get_config_value
from sense_common.ephemeral import EphemeralSource
from sense_common.models import SensorReading, SourceMetadata
from sense_common.redis_client import read_config

import redis.asyncio as aioredis
from pihole.client import PiHoleClient

logger = logging.getLogger(__name__)


class PiHoleSource(EphemeralSource):
    """Ephemeral source that fetches Pi-hole statistics."""

    @property
    def source_id(self) -> str:
        return "pihole"

    @property
    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            source_id="pihole",
            name="Pi-hole",
            description="Network-wide ad blocking statistics",
            refresh_interval=30,
        )

    async def poll(self, redis: aioredis.Redis) -> list[SensorReading]:
        """Fetch Pi-hole stats and return 3 readings."""
        config = await read_config(redis, "pihole")
        host = get_config_value(config, "PIHOLE_HOST", default="")
        password = get_config_value(config, "PIHOLE_PASSWORD", default="")

        if not host:
            logger.warning("No Pi-hole host configured")
            return []

        client_api = PiHoleClient(host, password)

        async with httpx.AsyncClient(timeout=5.0) as http_client:
            stats = await client_api.fetch_stats(http_client)

        if stats is None:
            logger.error("Failed to fetch Pi-hole stats")
            return []

        queries = stats.get("queries", {})
        return [
            SensorReading(
                sensor_id="queries_today",
                value=queries.get("total", 0),
                unit="queries",
            ),
            SensorReading(
                sensor_id="ads_blocked_today",
                value=queries.get("blocked", 0),
                unit="ads",
            ),
            SensorReading(
                sensor_id="ads_percentage_today",
                value=float(queries.get("percent_blocked", 0.0)),
                unit="%",
            ),
        ]
