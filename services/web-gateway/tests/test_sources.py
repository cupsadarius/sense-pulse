"""Tests for GET /api/sources endpoints."""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_all_sources(client: AsyncClient):
    """GET /api/sources returns merged readings + status for all sources."""
    resp = await client.get("/api/sources")
    assert resp.status_code == 200
    data = resp.json()

    # system source should have readings and status
    assert "system" in data
    assert "readings" in data["system"]
    assert "status" in data["system"]
    assert data["system"]["readings"]["cpu_percent"]["value"] == 23.5
    assert data["system"]["readings"]["cpu_percent"]["unit"] == "%"
    assert data["system"]["status"]["poll_count"] == 100

    # weather source
    assert "weather" in data
    assert data["weather"]["readings"]["weather_temp"]["value"] == 18.0
    assert data["weather"]["status"]["poll_count"] == 3


@pytest.mark.asyncio
async def test_get_single_source(client: AsyncClient):
    """GET /api/sources/{source_id} returns single source data."""
    resp = await client.get("/api/sources/system")
    assert resp.status_code == 200
    data = resp.json()
    assert "readings" in data
    assert "status" in data
    assert data["readings"]["cpu_percent"]["value"] == 23.5
    assert data["status"]["error_count"] == 0


@pytest.mark.asyncio
async def test_get_source_not_found(client: AsyncClient):
    """GET /api/sources/{source_id} returns 404 for unknown source."""
    resp = await client.get("/api/sources/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_source_with_status_no_readings(client: AsyncClient, fake_redis):
    """Source with status but no readings returns readings: {}."""
    await fake_redis.set(
        "status:orphan",
        json.dumps(
            {
                "source_id": "orphan",
                "last_poll": 1708000000.0,
                "last_success": None,
                "last_error": "init",
                "poll_count": 1,
                "error_count": 1,
            }
        ),
        ex=120,
    )
    resp = await client.get("/api/sources/orphan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["readings"] == {}
    assert data["status"]["poll_count"] == 1


@pytest.mark.asyncio
async def test_source_with_readings_no_status(client: AsyncClient, fake_redis):
    """Source with readings but expired status returns status: null."""
    await fake_redis.set(
        "source:sensors:temperature",
        json.dumps({"value": 24.3, "unit": "C", "timestamp": 1708000000.0}),
        ex=60,
    )
    # No status:sensors key
    resp = await client.get("/api/sources/sensors")
    assert resp.status_code == 200
    data = resp.json()
    assert data["readings"]["temperature"]["value"] == 24.3
    assert data["status"] is None


@pytest.mark.asyncio
async def test_get_all_sources_includes_status_only_source(client: AsyncClient, fake_redis):
    """GET /api/sources includes sources that have status but no readings."""
    await fake_redis.set(
        "status:orphan",
        json.dumps(
            {
                "source_id": "orphan",
                "last_poll": 1708000000.0,
                "last_success": None,
                "last_error": None,
                "poll_count": 0,
                "error_count": 0,
            }
        ),
        ex=120,
    )
    resp = await client.get("/api/sources")
    assert resp.status_code == 200
    data = resp.json()
    assert "orphan" in data
    assert data["orphan"]["readings"] == {}
