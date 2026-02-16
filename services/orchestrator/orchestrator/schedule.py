"""Scheduling logic for periodic source polling."""

from __future__ import annotations

import asyncio
import logging
import time

from orchestrator.runner import DockerRunner

logger = logging.getLogger(__name__)

# Tick interval in seconds
TICK_INTERVAL = 5.0

DEFAULT_SCHEDULES: dict[str, int] = {
    "source-tailscale": 30,
    "source-pihole": 30,
    "source-system": 30,
    "source-aranet4": 300,
    "source-weather": 600,
}


class Scheduler:
    """Triggers ephemeral source containers on configurable intervals."""

    def __init__(self, runner: DockerRunner, schedules: dict[str, int] | None = None) -> None:
        self.runner = runner
        self.schedules: dict[str, int] = dict(schedules or DEFAULT_SCHEDULES)
        # Initialize last_run to 0 so all services trigger immediately
        self.last_run: dict[str, float] = {svc: 0.0 for svc in self.schedules}
        self._shutdown = asyncio.Event()
        self._tasks: set[asyncio.Task[bool]] = set()

    def update_schedule(self, new_schedules: dict[str, int]) -> None:
        """Hot-reload schedule intervals.

        Updates existing services and adds new ones. Does not remove services.
        """
        for service, interval in new_schedules.items():
            key = f"source-{service}" if not service.startswith("source-") else service
            if key not in self.schedules or self.schedules[key] != interval:
                logger.info("Schedule updated: %s -> %ds", key, interval)
            self.schedules[key] = interval
            if key not in self.last_run:
                self.last_run[key] = 0.0

    async def run(self) -> None:
        """Main scheduling loop. Ticks every TICK_INTERVAL seconds."""
        logger.info("Scheduler started with %d services", len(self.schedules))
        try:
            while not self._shutdown.is_set():
                now = time.time()
                for service, interval in list(self.schedules.items()):
                    if now - self.last_run[service] >= interval:
                        if service not in self.runner.running:
                            self.last_run[service] = now
                            task = asyncio.create_task(
                                self.runner.run_ephemeral(service),
                                name=f"poll-{service}",
                            )
                            self._tasks.add(task)
                            task.add_done_callback(self._tasks.discard)

                try:
                    await asyncio.wait_for(
                        self._shutdown.wait(),
                        timeout=TICK_INTERVAL,
                    )
                    break  # shutdown was set
                except asyncio.TimeoutError:
                    pass  # normal tick
        finally:
            # Wait for any running tasks to finish
            if self._tasks:
                logger.info("Waiting for %d running tasks to finish...", len(self._tasks))
                await asyncio.gather(*self._tasks, return_exceptions=True)
            logger.info("Scheduler stopped")

    def stop(self) -> None:
        """Signal the scheduler to stop."""
        self._shutdown.set()
