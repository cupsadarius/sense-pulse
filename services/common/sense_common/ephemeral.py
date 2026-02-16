"""Base class for ephemeral (poll-and-die) source services."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

import redis.asyncio as aioredis

from sense_common.models import SensorReading, SourceMetadata, SourceStatus
from sense_common.redis_client import (
    create_redis,
    publish_data,
    write_metadata,
    write_readings,
    write_status,
)

logger = logging.getLogger(__name__)


class EphemeralSource(ABC):
    """Base class for ephemeral source services that poll once and exit."""

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique identifier for this source."""

    @property
    @abstractmethod
    def metadata(self) -> SourceMetadata:
        """Metadata describing this source."""

    @abstractmethod
    async def poll(self, redis: aioredis.Redis) -> list[SensorReading]:
        """Poll the data source and return readings.

        Receives the Redis client so implementations can read config.
        """

    async def run(self, redis_url: str) -> None:
        """Execute the full poll-and-die lifecycle."""
        redis: aioredis.Redis | None = None
        try:
            redis = await create_redis(redis_url)
            start = time.time()

            # Poll for data
            readings = await self.poll(redis)

            # Write results to Redis
            await write_readings(redis, self.source_id, readings)
            await write_metadata(redis, self.source_id, self.metadata)
            await write_status(
                redis,
                self.source_id,
                SourceStatus(
                    source_id=self.source_id,
                    last_poll=start,
                    last_success=time.time(),
                    poll_count=1,
                ),
            )
            await publish_data(redis, self.source_id)

            elapsed = time.time() - start
            logger.info(
                "[%s] Poll complete: %d readings in %.2fs",
                self.source_id,
                len(readings),
                elapsed,
            )

        except Exception as e:
            logger.exception("[%s] Poll failed: %s", self.source_id, e)
            if redis is not None:
                try:
                    await write_status(
                        redis,
                        self.source_id,
                        SourceStatus(
                            source_id=self.source_id,
                            last_poll=time.time(),
                            last_error=str(e),
                            error_count=1,
                        ),
                    )
                except Exception:
                    logger.exception("[%s] Failed to write error status", self.source_id)

        finally:
            if redis is not None:
                await redis.aclose()
