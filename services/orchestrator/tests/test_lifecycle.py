"""Tests for LifecycleListener."""

from __future__ import annotations

import asyncio
import contextlib
import json
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from orchestrator.lifecycle import LifecycleListener
from orchestrator.runner import DockerRunner


@pytest.fixture
async def redis():
    """Create a fakeredis instance."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def runner():
    r = DockerRunner(project_name="test")
    r.stop_service = AsyncMock(return_value=True)
    return r


@pytest.fixture
def listener(redis, runner):
    return LifecycleListener(redis, runner)


async def test_stream_ended_triggers_cleanup(redis, runner, listener):
    """stream:ended event should stop camera and update status."""
    # Start listener
    task = asyncio.create_task(listener.run())
    await asyncio.sleep(0.05)  # let it subscribe

    # Publish stream:ended event
    payload = json.dumps(
        {
            "source_id": "network_camera",
            "reason": "user_stopped",
            "timestamp": 1708000000.0,
        }
    )
    await redis.publish("stream:ended", payload)

    # Wait for cleanup (2s delay + processing)
    await asyncio.sleep(2.5)

    # Cancel listener
    listener.stop()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    # Verify stop was called
    runner.stop_service.assert_awaited_once_with("source-camera")

    # Verify status was updated
    status_raw = await redis.get("status:network_camera")
    assert status_raw is not None
    status = json.loads(status_raw)
    assert status["source_id"] == "network_camera"
    assert "user_stopped" in status["last_error"]


async def test_stream_ended_with_error_reason(redis, runner, listener):
    """stream:ended with error reason should still clean up."""
    task = asyncio.create_task(listener.run())
    await asyncio.sleep(0.05)

    payload = json.dumps(
        {
            "source_id": "network_camera",
            "reason": "ffmpeg_error",
            "timestamp": 1708000000.0,
        }
    )
    await redis.publish("stream:ended", payload)

    await asyncio.sleep(2.5)

    listener.stop()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    runner.stop_service.assert_awaited_once_with("source-camera")
    status_raw = await redis.get("status:network_camera")
    status = json.loads(status_raw)
    assert "ffmpeg_error" in status["last_error"]


async def test_lifecycle_stop(redis, runner, listener):
    """Listener should stop cleanly when stop() is called."""
    task = asyncio.create_task(listener.run())
    await asyncio.sleep(0.05)

    listener.stop()
    # Give it a moment to react
    await asyncio.sleep(0.1)

    # Should not hang -- cancel to be safe
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
