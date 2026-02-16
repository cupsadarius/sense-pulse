"""Shared fixtures for web gateway tests."""

from __future__ import annotations

import json
from typing import AsyncIterator

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient

from gateway.app import create_app


@pytest.fixture
async def fake_redis() -> AsyncIterator[fakeredis.aioredis.FakeRedis]:
    """Create a fakeredis instance with sample data pre-seeded."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    # Seed source readings
    await redis.set(
        "source:system:cpu_percent",
        json.dumps({"value": 23.5, "unit": "%", "timestamp": 1708000000.0}),
        ex=60,
    )
    await redis.set(
        "source:system:memory_percent",
        json.dumps({"value": 61.2, "unit": "%", "timestamp": 1708000000.0}),
        ex=60,
    )
    await redis.set(
        "source:weather:weather_temp",
        json.dumps({"value": 18.0, "unit": "C", "timestamp": 1708000000.0}),
        ex=60,
    )

    # Seed source statuses
    await redis.set(
        "status:system",
        json.dumps(
            {
                "source_id": "system",
                "last_poll": 1708000000.0,
                "last_success": 1708000000.0,
                "last_error": None,
                "poll_count": 100,
                "error_count": 0,
            }
        ),
        ex=120,
    )
    await redis.set(
        "status:weather",
        json.dumps(
            {
                "source_id": "weather",
                "last_poll": 1708000000.0,
                "last_success": 1708000000.0,
                "last_error": None,
                "poll_count": 3,
                "error_count": 0,
            }
        ),
        ex=120,
    )

    # Seed config sections
    await redis.set(
        "config:display",
        json.dumps({"rotation": 0, "scroll_speed": 0.08, "icon_duration": 1.5}),
    )
    await redis.set(
        "config:sleep",
        json.dumps({"start_hour": 23, "end_hour": 7, "disable_pi_leds": False}),
    )
    await redis.set(
        "config:auth",
        json.dumps({"enabled": False, "username": "admin", "password_hash": ""}),
    )

    yield redis
    await redis.aclose()


@pytest.fixture
async def app(fake_redis: fakeredis.aioredis.FakeRedis):
    """Create a FastAPI app with fakeredis injected."""
    application = create_app()
    application.state.redis = fake_redis
    return application


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
