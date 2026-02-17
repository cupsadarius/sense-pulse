"""Camera lifecycle management - handles stream:ended events."""

from __future__ import annotations

import asyncio
import json
import logging

from sense_common.models import SourceStatus
from sense_common.redis_client import write_status

import redis.asyncio as aioredis
from orchestrator.runner import DockerRunner

logger = logging.getLogger(__name__)

# Delay before stopping camera container after stream ends
CLEANUP_DELAY = 2.0


class LifecycleListener:
    """Listens for stream:ended events and cleans up camera containers."""

    def __init__(self, redis: aioredis.Redis, runner: DockerRunner) -> None:
        self.redis = redis
        self.runner = runner
        self._shutdown = asyncio.Event()

    async def run(self) -> None:
        """Subscribe to stream:ended and handle cleanup."""
        logger.info("Lifecycle listener started")
        pubsub = self.redis.pubsub()
        await pubsub.subscribe("stream:ended")
        try:
            async for message in pubsub.listen():
                if self._shutdown.is_set():
                    break
                if message["type"] != "message":
                    continue

                try:
                    payload = json.loads(message["data"])
                    reason = payload.get("reason", "unknown")
                    source_id = payload.get("source_id", "network_camera")
                    logger.info(
                        "Stream ended for %s, reason: %s",
                        source_id,
                        reason,
                    )
                except (json.JSONDecodeError, TypeError):
                    logger.error("Failed to parse stream:ended payload: %s", message["data"])
                    reason = "unknown"

                # Wait for container to finish cleanup
                await asyncio.sleep(CLEANUP_DELAY)

                # Stop the camera container
                await self.runner.stop_service("source-camera")

                # Update camera status to reflect stopped state
                status = SourceStatus(
                    source_id="network_camera",
                    last_error=f"Stream ended: {reason}",
                )
                await write_status(self.redis, "network_camera", status)

        except asyncio.CancelledError:
            logger.info("Lifecycle listener cancelled")
        finally:
            await pubsub.unsubscribe("stream:ended")
            await pubsub.aclose()
            logger.info("Lifecycle listener stopped")

    def stop(self) -> None:
        """Signal the listener to stop."""
        self._shutdown.set()
