"""Tests for config_seeder module."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import fakeredis.aioredis
import pytest

from orchestrator.config_seeder import seed_all_config


@pytest.fixture
async def redis():
    """Create a fakeredis instance."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def env_vars():
    """Standard set of environment variables for testing."""
    return {
        "PIHOLE_HOST": "http://pihole.local",
        "PIHOLE_PASSWORD": "secret123",
        "WEATHER_LOCATION": "London",
        "ARANET4_SENSORS": '[{"label": "office", "mac": "AA:BB:CC:DD:EE:FF"}]',
        "ARANET4_TIMEOUT": "15",
        "CAMERA_CONFIG": '[{"name": "cam1", "url": "rtsp://cam1"}]',
        "DISPLAY_ROTATION": "180",
        "SCROLL_SPEED": "0.1",
        "ICON_DURATION": "2.0",
        "SLEEP_START": "22",
        "SLEEP_END": "6",
        "DISABLE_PI_LEDS": "true",
        "SCHEDULE_TAILSCALE": "60",
        "SCHEDULE_PIHOLE": "45",
        "SCHEDULE_SYSTEM": "30",
        "SCHEDULE_ARANET4": "120",
        "SCHEDULE_WEATHER": "600",
        "AUTH_ENABLED": "true",
        "AUTH_USERNAME": "admin",
        "AUTH_PASSWORD_HASH": "$2b$12$hash",
    }


async def test_seed_all_config_writes_all_sections(redis, env_vars):
    """All env vars should be seeded into Redis."""
    with patch.dict(os.environ, env_vars, clear=False):
        results = await seed_all_config(redis)

    # All sections should have been written
    assert results["pihole"] is True
    assert results["weather"] is True
    assert results["aranet4"] is True
    assert results["camera"] is True
    assert results["display"] is True
    assert results["sleep"] is True
    assert results["schedule"] is True
    assert results["auth"] is True

    # Verify actual values in Redis
    pihole = json.loads(await redis.get("config:pihole"))
    assert pihole["host"] == "http://pihole.local"
    assert pihole["password"] == "secret123"

    weather = json.loads(await redis.get("config:weather"))
    assert weather["location"] == "London"

    aranet = json.loads(await redis.get("config:aranet4"))
    assert len(aranet["sensors"]) == 1
    assert aranet["sensors"][0]["label"] == "office"
    assert aranet["timeout"] == 15

    camera = json.loads(await redis.get("config:camera"))
    assert len(camera["cameras"]) == 1

    display = json.loads(await redis.get("config:display"))
    assert display["rotation"] == 180
    assert display["scroll_speed"] == 0.1
    assert display["icon_duration"] == 2.0

    sleep = json.loads(await redis.get("config:sleep"))
    assert sleep["start_hour"] == 22
    assert sleep["end_hour"] == 6
    assert sleep["disable_pi_leds"] is True

    schedule = json.loads(await redis.get("config:schedule"))
    assert schedule["tailscale"] == 60
    assert schedule["pihole"] == 45
    assert schedule["weather"] == 600

    auth = json.loads(await redis.get("config:auth"))
    assert auth["enabled"] is True
    assert auth["username"] == "admin"


async def test_seed_nx_does_not_overwrite(redis, env_vars):
    """Existing config keys should NOT be overwritten (NX behavior)."""
    # Pre-set a config value
    await redis.set("config:pihole", json.dumps({"host": "existing", "password": "old"}))

    with patch.dict(os.environ, env_vars, clear=False):
        results = await seed_all_config(redis)

    # pihole should NOT have been written (already existed)
    assert results["pihole"] is False

    # Verify the original value is preserved
    pihole = json.loads(await redis.get("config:pihole"))
    assert pihole["host"] == "existing"
    assert pihole["password"] == "old"

    # Other sections should have been written
    assert results["weather"] is True


async def test_seed_schedule_always_written(redis):
    """Schedule config should always be seeded (even with no env vars) with defaults."""
    # Clear all relevant env vars
    env = {
        "PIHOLE_HOST": "",
        "PIHOLE_PASSWORD": "",
        "WEATHER_LOCATION": "",
    }
    with patch.dict(os.environ, env, clear=False):
        results = await seed_all_config(redis)

    # Schedule should always be present (uses defaults)
    assert results["schedule"] is True
    schedule = json.loads(await redis.get("config:schedule"))
    assert schedule["tailscale"] == 30
    assert schedule["pihole"] == 30
    assert schedule["system"] == 30
    assert schedule["aranet4"] == 60
    assert schedule["weather"] == 300


async def test_seed_minimal_env(redis):
    """Only sections with env vars set should be seeded (except schedule)."""
    with patch.dict(os.environ, {"WEATHER_LOCATION": "Paris"}, clear=False):
        results = await seed_all_config(redis)

    assert results["weather"] is True
    assert results["schedule"] is True

    weather = json.loads(await redis.get("config:weather"))
    assert weather["location"] == "Paris"
