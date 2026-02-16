"""Configuration helpers for Sense Pulse services."""

from __future__ import annotations

import json
import os
from typing import Any


def get_env(key: str, default: str = "") -> str:
    """Get an environment variable as a string."""
    return os.environ.get(key, default)


def get_env_int(key: str, default: int = 0) -> int:
    """Get an environment variable as an integer."""
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def get_env_float(key: str, default: float = 0.0) -> float:
    """Get an environment variable as a float."""
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def get_env_bool(key: str, default: bool = False) -> bool:
    """Get an environment variable as a boolean.

    Truthy values: "true", "1", "yes" (case-insensitive).
    """
    val = os.environ.get(key)
    if val is None:
        return default
    return val.lower() in ("true", "1", "yes")


def get_env_json(key: str, default: Any = None) -> Any:
    """Get an environment variable as parsed JSON."""
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return default


def get_redis_url() -> str:
    """Get the Redis URL from environment. Defaults to redis://redis:6379."""
    return os.environ.get("REDIS_URL", "redis://redis:6379")


def get_config_value(
    redis_config: dict[str, Any] | None,
    env_key: str,
    default: Any = None,
    *,
    config_key: str | None = None,
) -> Any:
    """Get a config value with Redis-first, env-fallback pattern.

    Args:
        redis_config: Config dict from Redis (may be None).
        env_key: Environment variable name to fall back to.
        default: Default value if both Redis and env are missing.
        config_key: Key to look up in redis_config. If None, derives from env_key
                     by lowercasing and removing common prefixes.
    """
    # Try Redis config first
    if redis_config is not None:
        key = config_key
        if key is None:
            # Derive config key: WEATHER_LOCATION -> location, PIHOLE_HOST -> host
            key = env_key.lower()
            for prefix in (
                "weather_",
                "pihole_",
                "aranet4_",
                "camera_",
                "display_",
                "sleep_",
                "schedule_",
                "auth_",
            ):
                if key.startswith(prefix):
                    key = key[len(prefix) :]
                    break
        if key in redis_config:
            return redis_config[key]

    # Fall back to environment variable
    env_val = os.environ.get(env_key)
    if env_val is not None:
        # Try to parse as JSON for complex types
        if isinstance(default, list | dict):
            try:
                return json.loads(env_val)
            except (json.JSONDecodeError, TypeError):
                return default
        if isinstance(default, bool):
            return env_val.lower() in ("true", "1", "yes")
        if isinstance(default, int):
            try:
                return int(env_val)
            except ValueError:
                return default
        if isinstance(default, float):
            try:
                return float(env_val)
            except ValueError:
                return default
        return env_val

    return default
