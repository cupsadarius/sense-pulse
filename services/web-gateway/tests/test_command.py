"""Tests for POST /api/command/{target} endpoint."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_command_unknown_target(client: AsyncClient):
    """POST /api/command/unknown returns 400."""
    resp = await client.post("/api/command/unknown", json={"action": "test"})
    assert resp.status_code == 400
    assert "Unknown target" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_command_missing_action(client: AsyncClient):
    """POST /api/command/sensors without action returns 400."""
    resp = await client.post("/api/command/sensors", json={})
    assert resp.status_code == 400
    assert "action" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_command_timeout(client: AsyncClient, fake_redis):
    """POST /api/command/sensors times out if no response published."""
    # Reduce the default timeout so the test doesn't wait 5s
    with patch("gateway.routes.command.DEFAULT_TIMEOUT", 0.5):
        resp = await client.post("/api/command/sensors", json={"action": "clear"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "timeout" in data["message"].lower() or "Timeout" in data["message"]


@pytest.mark.asyncio
async def test_command_with_response(client: AsyncClient, fake_redis):
    """POST /api/command/sensors returns success when response arrives."""
    # Subscribe to cmd:sensors to catch the command and respond
    pubsub = fake_redis.pubsub()
    await pubsub.subscribe("cmd:sensors")

    async def respond():
        """Wait for command and publish response."""
        # Wait for the command message
        for _ in range(100):
            msg = await pubsub.get_message(ignore_subscribe_messages=True)
            if msg and msg["type"] == "message":
                command = json.loads(msg["data"])
                request_id = command["request_id"]
                response_channel = f"cmd:sensors:response:{request_id}"
                response_payload = json.dumps(
                    {
                        "request_id": request_id,
                        "status": "ok",
                        "data": {"message": "Display cleared"},
                        "error": None,
                    }
                )
                await fake_redis.publish(response_channel, response_payload)
                return
            await asyncio.sleep(0.02)

    # Launch responder and request concurrently
    resp_task = asyncio.create_task(respond())
    resp = await client.post("/api/command/sensors", json={"action": "clear"})
    await resp_task

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["message"] == "Display cleared"

    await pubsub.unsubscribe("cmd:sensors")
    await pubsub.aclose()
