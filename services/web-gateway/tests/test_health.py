"""Tests for GET /health endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_ok(client: AsyncClient):
    """Health returns 200 when Redis is reachable."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_health_no_auth(client: AsyncClient):
    """Health endpoint does not require auth."""
    resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_redis_down(app):
    """Health returns 503 when Redis ping fails."""
    from unittest.mock import AsyncMock

    from httpx import ASGITransport, AsyncClient

    # Replace redis with a mock that raises on ping
    mock_redis = AsyncMock()
    mock_redis.ping.side_effect = ConnectionError("Redis down")
    app.state.redis = mock_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/health")
        assert resp.status_code == 503
        assert resp.json() == {"status": "unhealthy"}
