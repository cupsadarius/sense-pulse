"""Orchestrator service entry point."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from sense_common.config import get_env, get_env_int, get_redis_url
from sense_common.redis_client import create_redis, read_config, subscribe_config_changes

from orchestrator.commands import CommandListener
from orchestrator.config_seeder import seed_all_config
from orchestrator.health import HealthMonitor
from orchestrator.lifecycle import LifecycleListener
from orchestrator.runner import DockerRunner
from orchestrator.schedule import Scheduler

logger = logging.getLogger(__name__)


def _build_schedules() -> dict[str, int]:
    """Build schedule dict from env with defaults."""
    return {
        "source-tailscale": get_env_int("SCHEDULE_TAILSCALE", 30),
        "source-pihole": get_env_int("SCHEDULE_PIHOLE", 30),
        "source-system": get_env_int("SCHEDULE_SYSTEM", 30),
        "source-aranet4": get_env_int("SCHEDULE_ARANET4", 300),
        "source-weather": get_env_int("SCHEDULE_WEATHER", 600),
    }


async def _config_change_listener(
    redis_url: str,
    scheduler: Scheduler,
    runner: DockerRunner,
) -> None:
    """Listen for config:changed events and act on them."""
    # Use a separate Redis connection for pub/sub
    redis = await create_redis(redis_url)
    try:
        logger.info("Config change listener started")
        async for section in subscribe_config_changes(redis):
            if section == "schedule":
                config = await read_config(redis, "schedule")
                if config:
                    scheduler.update_schedule(config)
                    logger.info("Schedule updated from config change")
            elif section == "auth":
                logger.warning("Auth config changed, web-gateway restart may be required")
            elif section == "camera":
                if "source-camera" in runner.running:
                    logger.warning("Camera config changed, restart stream to apply")
            else:
                logger.debug("Config changed for section: %s (no action needed)", section)
    except asyncio.CancelledError:
        logger.info("Config change listener cancelled")
    finally:
        await redis.aclose()


async def run() -> None:
    """Start all orchestrator components and run until shutdown."""
    redis_url = get_redis_url()
    project_name = get_env("COMPOSE_PROJECT_NAME", "sense-pulse")

    # Connect to Redis
    redis = await create_redis(redis_url)

    try:
        # Seed config from env on first boot
        results = await seed_all_config(redis)
        seeded = [s for s, written in results.items() if written]
        if seeded:
            logger.info("Seeded config sections: %s", ", ".join(seeded))

        # Load schedule from Redis (may have been seeded or previously set)
        schedule_config = await read_config(redis, "schedule")
        if schedule_config:
            schedules: dict[str, int] = {}
            for key, val in schedule_config.items():
                svc = f"source-{key}" if not key.startswith("source-") else key
                if isinstance(val, int):
                    schedules[svc] = val
            # Merge with env defaults for any missing keys
            for svc, interval in _build_schedules().items():
                schedules.setdefault(svc, interval)
        else:
            schedules = _build_schedules()

        # Create components
        runner = DockerRunner(project_name)
        scheduler = Scheduler(runner, schedules)
        command_listener = CommandListener(redis, runner)
        lifecycle_listener = LifecycleListener(redis, runner)
        health_monitor = HealthMonitor(redis)

        # Shutdown handling
        shutdown_event = asyncio.Event()

        def _signal_handler() -> None:
            logger.info("Shutdown signal received")
            shutdown_event.set()
            scheduler.stop()
            command_listener.stop()
            lifecycle_listener.stop()
            health_monitor.stop()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _signal_handler)

        # Run all concurrently
        tasks = [
            asyncio.create_task(scheduler.run(), name="scheduler"),
            asyncio.create_task(command_listener.run(), name="command-listener"),
            asyncio.create_task(lifecycle_listener.run(), name="lifecycle-listener"),
            asyncio.create_task(
                _config_change_listener(redis_url, scheduler, runner),
                name="config-change-listener",
            ),
            asyncio.create_task(health_monitor.run(), name="health-monitor"),
        ]

        logger.info("Orchestrator started")

        # Wait for shutdown signal
        await shutdown_event.wait()

        # Cancel all tasks
        for task in tasks:
            task.cancel()

        # Wait for tasks to finish (up to 30s)
        await asyncio.wait(tasks, timeout=30.0)

    finally:
        await redis.aclose()
        logger.info("Orchestrator stopped")


def main() -> None:
    """Entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    )
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":
    main()
