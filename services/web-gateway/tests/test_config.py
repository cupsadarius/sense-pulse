"""Tests for GET/POST /api/config endpoints."""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_config(client: AsyncClient):
    """GET /api/config returns all config sections from Redis."""
    resp = await client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()

    assert "display" in data
    assert data["display"]["rotation"] == 0
    assert data["display"]["scroll_speed"] == 0.08

    assert "sleep" in data
    assert data["sleep"]["start_hour"] == 23

    # Auth section should have password_hash stripped
    assert "auth" in data
    assert "password_hash" not in data["auth"]
    assert data["auth"]["enabled"] is False


@pytest.mark.asyncio
async def test_post_config_partial_update(client: AsyncClient, fake_redis):
    """POST /api/config updates specified sections and publishes changes."""
    # Subscribe to config:changed to verify publish
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe("config:changed")

    resp = await client.post(
        "/api/config",
        json={"display": {"rotation": 180}, "sleep": {"start_hour": 22}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert set(data["sections_updated"]) == {"display", "sleep"}

    # Verify Redis was updated (merged with existing)
    display_raw = await fake_redis.get("config:display")
    display = json.loads(display_raw)
    assert display["rotation"] == 180
    assert display["scroll_speed"] == 0.08  # preserved from original

    sleep_raw = await fake_redis.get("config:sleep")
    sleep = json.loads(sleep_raw)
    assert sleep["start_hour"] == 22
    assert sleep["end_hour"] == 7  # preserved from original

    await pubsub.unsubscribe("config:changed")
    await pubsub.aclose()


@pytest.mark.asyncio
async def test_post_config_unknown_section_ignored(client: AsyncClient):
    """POST /api/config ignores unknown config sections."""
    resp = await client.post("/api/config", json={"unknown_thing": {"foo": "bar"}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["sections_updated"] == []


@pytest.mark.asyncio
async def test_post_config_new_section(client: AsyncClient, fake_redis):
    """POST /api/config creates section if it doesn't exist in Redis yet."""
    resp = await client.post("/api/config", json={"weather": {"location": "Paris"}})
    assert resp.status_code == 200
    data = resp.json()
    assert "weather" in data["sections_updated"]

    weather_raw = await fake_redis.get("config:weather")
    weather = json.loads(weather_raw)
    assert weather["location"] == "Paris"
