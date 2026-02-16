"""Entry point for the Aranet4 source service.

Supports two modes via MODE env var:
- MODE=poll (default): Read configured sensors, write readings to Redis, exit.
- MODE=scan: Discover nearby Aranet4 BLE devices, write to scan:co2 Redis key, exit.
"""

from __future__ import annotations

import asyncio
import json
import logging

from sense_common.config import get_config_value, get_env, get_redis_url
from sense_common.redis_client import create_redis, read_config

from aranet4_svc.scanner import Aranet4Scanner
from aranet4_svc.source import Aranet4Source

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

SCAN_KEY = "scan:co2"
SCAN_TTL = 60  # seconds


async def run_scan_mode() -> None:
    """Discover nearby Aranet4 devices and write results to Redis."""
    redis_url = get_redis_url()
    redis = await create_redis(redis_url)

    try:
        config = await read_config(redis, "aranet4")
        timeout: int = get_config_value(config, "ARANET4_TIMEOUT", default=10)

        scanner = Aranet4Scanner()
        devices = await scanner.discover(timeout=timeout)

        # Write discovered devices to Redis with TTL
        await redis.set(SCAN_KEY, json.dumps(devices), ex=SCAN_TTL)
        logger.info("Scan mode: wrote %d devices to %s", len(devices), SCAN_KEY)
    finally:
        await redis.aclose()


async def run_poll_mode() -> None:
    """Normal ephemeral poll: read sensors, write readings, exit."""
    source = Aranet4Source()
    await source.run(get_redis_url())


def main() -> None:
    mode = get_env("MODE", "poll").lower()
    logger.info("Aranet4 service starting in %s mode", mode)

    if mode == "scan":
        asyncio.run(run_scan_mode())
    else:
        asyncio.run(run_poll_mode())


if __name__ == "__main__":
    main()
