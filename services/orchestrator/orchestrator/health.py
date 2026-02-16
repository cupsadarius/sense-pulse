"""Health monitoring for all source services."""

from __future__ import annotations

import asyncio
import logging
import time

import redis.asyncio as aioredis

from sense_common.models import SourceStatus
from sense_common.redis_client import read_all_statuses, read_config, write_status

logger = logging.getLogger(__name__)

# How often to check health (seconds)
CHECK_INTERVAL = 60.0

# If a source hasn't reported in 3x its interval, it's considered overdue
OVERDUE_MULTIPLIER = 3


class HealthMonitor:
    """Periodically checks source health and reports orchestrator status."""

    def __init__(self, redis: aioredis.Redis) -> None:
        self.redis = redis
        self._shutdown = asyncio.Event()
        self._poll_count = 0

    async def run(self) -> None:
        """Main health check loop."""
        logger.info("Health monitor started (interval: %.0fs)", CHECK_INTERVAL)
        try:
            while not self._shutdown.is_set():
                await self._check_health()
                try:
                    await asyncio.wait_for(
                        self._shutdown.wait(),
                        timeout=CHECK_INTERVAL,
                    )
                    break  # shutdown was set
                except asyncio.TimeoutError:
                    pass  # normal tick
        except asyncio.CancelledError:
            logger.info("Health monitor cancelled")
        finally:
            logger.info("Health monitor stopped")

    async def _check_health(self) -> None:
        """Run a single health check cycle."""
        self._poll_count += 1
        now = time.time()

        # Read schedule config for expected intervals
        schedule_config = await read_config(self.redis, "schedule") or {}
        default_intervals: dict[str, int] = {
            "tailscale": 30,
            "pihole": 30,
            "system": 30,
            "co2": 60,
            "weather": 300,
        }

        # Merge schedule config (uses source names without "source-" prefix)
        intervals: dict[str, int] = {**default_intervals}
        for key, val in schedule_config.items():
            # Map aranet4 schedule -> co2 source_id
            mapped = "co2" if key == "aranet4" else key
            if isinstance(val, int):
                intervals[mapped] = val

        # Read all statuses
        statuses = await read_all_statuses(self.redis)
        overdue: list[str] = []

        for status in statuses:
            if status.source_id == "orchestrator":
                continue
            interval = intervals.get(status.source_id, 60)
            threshold = interval * OVERDUE_MULTIPLIER
            if status.last_success is not None and (now - status.last_success) > threshold:
                overdue.append(status.source_id)
                logger.warning(
                    "Source %s is overdue: last success %.0fs ago (threshold: %ds)",
                    status.source_id,
                    now - status.last_success,
                    threshold,
                )

        # Write own status
        own_status = SourceStatus(
            source_id="orchestrator",
            last_poll=now,
            last_success=now,
            poll_count=self._poll_count,
            last_error=f"Overdue sources: {', '.join(overdue)}" if overdue else None,
        )
        await write_status(self.redis, "orchestrator", own_status)

        if not overdue:
            logger.debug("Health check OK: all sources within thresholds")

    def stop(self) -> None:
        """Signal the monitor to stop."""
        self._shutdown.set()
