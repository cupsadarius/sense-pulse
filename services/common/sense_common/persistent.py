"""Base class for persistent (always-running) source services."""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from abc import ABC, abstractmethod

import redis.asyncio as aioredis
from sense_common.models import (
    Command,
    CommandResponse,
    SensorReading,
    SourceMetadata,
    SourceStatus,
)
from sense_common.redis_client import (
    create_redis,
    publish_data,
    publish_response,
    subscribe_commands,
    subscribe_config_changes,
    write_metadata,
    write_readings,
    write_status,
)

logger = logging.getLogger(__name__)


class PersistentSource(ABC):
    """Base class for always-running source services."""

    def __init__(self) -> None:
        self._shutdown_event = asyncio.Event()
        self._poll_count = 0
        self._error_count = 0

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
        """Poll the data source and return readings."""

    @abstractmethod
    async def handle_command(self, command: Command) -> CommandResponse:
        """Handle a command from Redis pub/sub."""

    async def on_config_changed(self, redis: aioredis.Redis, section: str) -> None:  # noqa: B027
        """Called when a config section changes. Override for hot-reload."""

    async def run(self, redis_url: str, poll_interval: int = 30) -> None:
        """Run the persistent service with concurrent tasks."""
        redis = await create_redis(redis_url)

        # Install signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._shutdown_event.set)

        try:
            # Write initial metadata
            await write_metadata(redis, self.source_id, self.metadata)

            # Run all tasks concurrently
            await asyncio.gather(
                self._poll_loop(redis, poll_interval),
                self._command_listener(redis),
                self._config_listener(redis),
                return_exceptions=True,
            )
        finally:
            await redis.aclose()

    async def _poll_loop(self, redis: aioredis.Redis, interval: int) -> None:
        """Poll on interval, writing readings to Redis."""
        while not self._shutdown_event.is_set():
            start = time.time()
            try:
                readings = await self.poll(redis)
                self._poll_count += 1

                await write_readings(redis, self.source_id, readings)
                await write_status(
                    redis,
                    self.source_id,
                    SourceStatus(
                        source_id=self.source_id,
                        last_poll=start,
                        last_success=time.time(),
                        poll_count=self._poll_count,
                        error_count=self._error_count,
                    ),
                )
                await publish_data(redis, self.source_id)

                logger.debug(
                    "[%s] Poll %d: %d readings",
                    self.source_id,
                    self._poll_count,
                    len(readings),
                )

            except Exception as e:
                self._error_count += 1
                logger.exception("[%s] Poll error: %s", self.source_id, e)
                try:
                    await write_status(
                        redis,
                        self.source_id,
                        SourceStatus(
                            source_id=self.source_id,
                            last_poll=start,
                            last_error=str(e),
                            poll_count=self._poll_count,
                            error_count=self._error_count,
                        ),
                    )
                except Exception:
                    logger.exception("[%s] Failed to write error status", self.source_id)

            # Wait for next poll or shutdown
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=interval,
                )
                break  # shutdown requested
            except TimeoutError:
                pass  # time to poll again

    async def _command_listener(self, redis: aioredis.Redis) -> None:
        """Listen for commands on Redis pub/sub."""
        while not self._shutdown_event.is_set():
            try:
                async for command in subscribe_commands(redis, self.source_id):
                    if self._shutdown_event.is_set():
                        break
                    try:
                        response = await self.handle_command(command)
                        await publish_response(redis, self.source_id, response)
                    except Exception as e:
                        logger.exception("[%s] Command handler error: %s", self.source_id, e)
                        await publish_response(
                            redis,
                            self.source_id,
                            CommandResponse(
                                request_id=command.request_id,
                                status="error",
                                error=str(e),
                            ),
                        )
            except Exception:
                if not self._shutdown_event.is_set():
                    logger.exception("[%s] Command listener error, reconnecting...", self.source_id)
                    await asyncio.sleep(1)

    async def _config_listener(self, redis: aioredis.Redis) -> None:
        """Listen for config change notifications."""
        while not self._shutdown_event.is_set():
            try:
                async for section in subscribe_config_changes(redis):
                    if self._shutdown_event.is_set():
                        break
                    try:
                        await self.on_config_changed(redis, section)
                    except Exception:
                        logger.exception(
                            "[%s] Config change handler error for section '%s'",
                            self.source_id,
                            section,
                        )
            except Exception:
                if not self._shutdown_event.is_set():
                    logger.exception("[%s] Config listener error, reconnecting...", self.source_id)
                    await asyncio.sleep(1)
