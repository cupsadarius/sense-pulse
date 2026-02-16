"""Seed Redis config from environment variables on first boot."""

from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as aioredis

from sense_common.config import (
    get_env,
    get_env_bool,
    get_env_float,
    get_env_int,
    get_env_json,
)
from sense_common.redis_client import seed_config_from_env

logger = logging.getLogger(__name__)


def _build_config_map() -> dict[str, dict[str, Any]]:
    """Build a mapping of config section -> data from environment variables.

    Only includes sections where at least one env var is set.
    """
    configs: dict[str, dict[str, Any]] = {}

    # config:pihole
    pihole_host = get_env("PIHOLE_HOST")
    pihole_password = get_env("PIHOLE_PASSWORD")
    if pihole_host or pihole_password:
        configs["pihole"] = {"host": pihole_host, "password": pihole_password}

    # config:weather
    weather_location = get_env("WEATHER_LOCATION")
    if weather_location:
        configs["weather"] = {"location": weather_location}

    # config:aranet4
    aranet4_sensors = get_env_json("ARANET4_SENSORS", [])
    aranet4_timeout = get_env_int("ARANET4_TIMEOUT", 10)
    if aranet4_sensors or get_env("ARANET4_SENSORS"):
        configs["aranet4"] = {"sensors": aranet4_sensors, "timeout": aranet4_timeout}

    # config:camera
    camera_config = get_env_json("CAMERA_CONFIG", [])
    if camera_config or get_env("CAMERA_CONFIG"):
        configs["camera"] = {"cameras": camera_config}

    # config:display
    display_rotation = get_env_int("DISPLAY_ROTATION", 0)
    scroll_speed = get_env_float("SCROLL_SPEED", 0.08)
    icon_duration = get_env_float("ICON_DURATION", 1.5)
    if get_env("DISPLAY_ROTATION") or get_env("SCROLL_SPEED") or get_env("ICON_DURATION"):
        configs["display"] = {
            "rotation": display_rotation,
            "scroll_speed": scroll_speed,
            "icon_duration": icon_duration,
        }

    # config:sleep
    sleep_start = get_env_int("SLEEP_START", 23)
    sleep_end = get_env_int("SLEEP_END", 7)
    disable_pi_leds = get_env_bool("DISABLE_PI_LEDS", False)
    if get_env("SLEEP_START") or get_env("SLEEP_END") or get_env("DISABLE_PI_LEDS"):
        configs["sleep"] = {
            "start_hour": sleep_start,
            "end_hour": sleep_end,
            "disable_pi_leds": disable_pi_leds,
        }

    # config:schedule
    schedule: dict[str, int] = {}
    for source, default in [
        ("tailscale", 30),
        ("pihole", 30),
        ("system", 30),
        ("aranet4", 60),
        ("weather", 300),
    ]:
        env_key = f"SCHEDULE_{source.upper()}"
        schedule[source] = get_env_int(env_key, default)
    configs["schedule"] = schedule

    # config:auth
    auth_enabled = get_env_bool("AUTH_ENABLED", True)
    auth_username = get_env("AUTH_USERNAME")
    auth_password_hash = get_env("AUTH_PASSWORD_HASH")
    if get_env("AUTH_ENABLED") or auth_username or auth_password_hash:
        configs["auth"] = {
            "enabled": auth_enabled,
            "username": auth_username,
            "password_hash": auth_password_hash,
        }

    return configs


async def seed_all_config(redis: aioredis.Redis) -> dict[str, bool]:
    """Seed all config sections from environment variables using SET NX.

    Returns a dict of section -> whether it was written (True) or already existed (False).
    """
    config_map = _build_config_map()
    results: dict[str, bool] = {}

    for section, data in config_map.items():
        written = await seed_config_from_env(redis, section, data)
        results[section] = written
        if written:
            logger.info("Seeded config:%s from environment", section)
        else:
            logger.debug("config:%s already exists, skipping seed", section)

    return results
