"""Entry point for the Sense HAT service -- runs all concurrent tasks."""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import time

import redis.asyncio as aioredis

from sense_common.config import get_env_float, get_env_int, get_redis_url
from sense_common.models import SensorReading, SourceMetadata, SourceStatus
from sense_common.redis_client import (
    create_redis,
    publish_data,
    read_config,
    subscribe_config_changes,
    write_metadata,
    write_readings,
    write_status,
)
from sensehat.commands import CommandHandler
from sensehat.controller import DisplayController
from sensehat.display import SenseHatDisplay
from sensehat.pi_leds import disable_leds, restore_leds
from sensehat.source import SenseHatSensorSource

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SOURCE_ID = "sensors"
POLL_INTERVAL = 30


async def sensor_poll_loop(
    redis: aioredis.Redis,
    source: SenseHatSensorSource,
    shutdown: asyncio.Event,
) -> None:
    """Poll sensors and write to Redis on interval."""
    metadata = SourceMetadata(
        source_id=SOURCE_ID,
        name="Sense HAT Sensors",
        description="Onboard temperature, humidity, and pressure sensors",
        refresh_interval=POLL_INTERVAL,
    )
    await write_metadata(redis, SOURCE_ID, metadata)

    poll_count = 0
    error_count = 0

    while not shutdown.is_set():
        start = time.time()
        try:
            readings = await source.poll()
            poll_count += 1
            await write_readings(redis, SOURCE_ID, readings)
            await write_status(
                redis,
                SOURCE_ID,
                SourceStatus(
                    source_id=SOURCE_ID,
                    last_poll=start,
                    last_success=time.time(),
                    poll_count=poll_count,
                    error_count=error_count,
                ),
            )
            await publish_data(redis, SOURCE_ID)
            logger.debug("Sensor poll %d: %d readings", poll_count, len(readings))
        except Exception as e:
            error_count += 1
            logger.exception("Sensor poll error: %s", e)
            try:
                await write_status(
                    redis,
                    SOURCE_ID,
                    SourceStatus(
                        source_id=SOURCE_ID,
                        last_poll=start,
                        last_error=str(e),
                        poll_count=poll_count,
                        error_count=error_count,
                    ),
                )
            except Exception:
                pass

        try:
            await asyncio.wait_for(shutdown.wait(), timeout=POLL_INTERVAL)
            break
        except asyncio.TimeoutError:
            pass


async def display_cycle_loop(
    redis: aioredis.Redis,
    controller: DisplayController,
    shutdown: asyncio.Event,
) -> None:
    """Continuously cycle through sources on the LED display."""
    while not shutdown.is_set():
        try:
            await controller.run_cycle(redis)
        except Exception:
            logger.exception("Display cycle error")
            await asyncio.sleep(5)


async def config_change_listener(
    redis: aioredis.Redis,
    controller: DisplayController,
    display: SenseHatDisplay,
    shutdown: asyncio.Event,
) -> None:
    """Listen for config changes and hot-reload display/sleep settings."""
    while not shutdown.is_set():
        try:
            async for section in subscribe_config_changes(redis):
                if shutdown.is_set():
                    break
                try:
                    if section == "display":
                        cfg = await read_config(redis, "display")
                        if cfg:
                            if "rotation" in cfg:
                                display.set_rotation(cfg["rotation"])
                            if "scroll_speed" in cfg:
                                display.scroll_speed = cfg["scroll_speed"]
                            if "icon_duration" in cfg:
                                display.icon_duration = cfg["icon_duration"]
                            logger.info("Display config reloaded: %s", cfg)
                    elif section == "sleep":
                        cfg = await read_config(redis, "sleep")
                        if cfg:
                            controller.sleep_start = cfg.get("start_hour", controller.sleep_start)
                            controller.sleep_end = cfg.get("end_hour", controller.sleep_end)
                            logger.info(
                                "Sleep config reloaded: start=%d end=%d",
                                controller.sleep_start,
                                controller.sleep_end,
                            )
                except Exception:
                    logger.exception("Error handling config change for %s", section)
        except Exception:
            if not shutdown.is_set():
                logger.exception("Config listener error, reconnecting...")
                await asyncio.sleep(1)


async def matrix_state_publisher(
    redis: aioredis.Redis,
    display: SenseHatDisplay,
    shutdown: asyncio.Event,
) -> None:
    """Publish LED matrix state every 500ms for web preview."""
    while not shutdown.is_set():
        try:
            pixels = display.get_pixels()
            payload = json.dumps(
                {
                    "pixels": pixels,
                    "mode": display.current_mode,
                    "rotation": display.rotation,
                    "available": display.sense is not None,
                }
            )
            await redis.publish("matrix:state", payload)
        except Exception:
            logger.debug("Failed to publish matrix state", exc_info=True)

        try:
            await asyncio.wait_for(shutdown.wait(), timeout=0.5)
            break
        except asyncio.TimeoutError:
            pass


async def async_main() -> None:
    """Main entry point."""
    redis_url = get_redis_url()
    redis = await create_redis(redis_url)
    shutdown = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown.set)

    # Initialize sensor source
    source = SenseHatSensorSource()
    await source.initialize()

    # Read initial config
    display_config = await read_config(redis, "display") or {}
    sleep_config = await read_config(redis, "sleep") or {}

    rotation = display_config.get("rotation", get_env_int("DISPLAY_ROTATION", 0))
    scroll_speed = display_config.get("scroll_speed", get_env_float("SCROLL_SPEED", 0.08))
    icon_duration = display_config.get("icon_duration", get_env_float("ICON_DURATION", 1.5))
    sleep_start = sleep_config.get("start_hour", get_env_int("SLEEP_START", 23))
    sleep_end = sleep_config.get("end_hour", get_env_int("SLEEP_END", 7))

    # Create display and controller
    display = SenseHatDisplay(
        sense_hat_instance=source.sense_hat,
        rotation=rotation,
        scroll_speed=scroll_speed,
        icon_duration=icon_duration,
    )
    controller = DisplayController(display=display, sleep_start=sleep_start, sleep_end=sleep_end)
    cmd_handler = CommandHandler(display=display)

    logger.info("Starting Sense HAT service (hardware=%s)", source.is_available)

    try:
        await asyncio.gather(
            sensor_poll_loop(redis, source, shutdown),
            display_cycle_loop(redis, controller, shutdown),
            cmd_handler.listen(redis, shutdown),
            config_change_listener(redis, controller, display, shutdown),
            matrix_state_publisher(redis, display, shutdown),
        )
    finally:
        await display.clear()
        await redis.aclose()
        logger.info("Sense HAT service stopped")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
