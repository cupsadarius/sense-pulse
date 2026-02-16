"""Tests for CommandListener."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest

from sense_common.models import Command, CommandResponse

from orchestrator.commands import CommandListener
from orchestrator.runner import DockerRunner


@pytest.fixture
async def redis():
    """Create a fakeredis instance."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def runner():
    return DockerRunner(project_name="test")


@pytest.fixture
def listener(redis, runner):
    return CommandListener(redis, runner)


async def test_handle_start_camera(listener, runner):
    """start_camera should call runner.start_service."""
    runner.start_service = AsyncMock(return_value=True)

    command = Command(action="start_camera", request_id="req-1")
    response = await listener._handle_command(command)

    runner.start_service.assert_awaited_once_with("source-camera")
    # Check published response
    assert response is None  # response is published, not returned

    # Actually test the handler directly
    resp = await listener._handle_start_camera(command)
    assert resp.status == "ok"
    assert resp.request_id == "req-1"


async def test_handle_start_camera_failure(listener, runner):
    """start_camera failure returns error."""
    runner.start_service = AsyncMock(return_value=False)

    command = Command(action="start_camera", request_id="req-2")
    resp = await listener._handle_start_camera(command)
    assert resp.status == "error"
    assert "Failed" in resp.error


async def test_handle_stop_camera(listener, redis):
    """stop_camera should publish stop command to camera."""
    # Track published messages
    published = []
    original_publish = redis.publish

    async def track_publish(channel, data):
        published.append((channel, data))
        return await original_publish(channel, data)

    redis.publish = track_publish

    command = Command(action="stop_camera", request_id="req-3")
    resp = await listener._handle_stop_camera(command)

    assert resp.status == "ok"
    assert resp.request_id == "req-3"
    # Should have published to cmd:network_camera
    assert any(ch == "cmd:network_camera" for ch, _ in published)


async def test_handle_trigger(listener, runner):
    """trigger should run the specified service."""
    runner.run_ephemeral = AsyncMock(return_value=True)

    command = Command(action="trigger", request_id="req-4", params={"service": "source-weather"})
    resp = await listener._handle_trigger(command)

    assert resp.status == "ok"
    runner.run_ephemeral.assert_awaited_once_with("source-weather")


async def test_handle_trigger_missing_service(listener):
    """trigger without service parameter returns error."""
    command = Command(action="trigger", request_id="req-5", params={})
    resp = await listener._handle_trigger(command)

    assert resp.status == "error"
    assert "Missing" in resp.error


async def test_handle_scan_aranet4(listener, runner, redis):
    """scan_aranet4 should run with MODE=scan and read results."""
    runner.run_ephemeral = AsyncMock(return_value=True)

    # Pre-set scan results
    devices = [{"name": "Aranet4 12345", "mac": "AA:BB:CC:DD:EE:FF", "rssi": -60}]
    await redis.set("scan:co2", json.dumps(devices))

    command = Command(action="scan_aranet4", request_id="req-6")
    resp = await listener._handle_scan_aranet4(command)

    assert resp.status == "ok"
    assert len(resp.data["devices"]) == 1
    assert resp.data["devices"][0]["name"] == "Aranet4 12345"
    runner.run_ephemeral.assert_awaited_once_with("source-aranet4", env={"MODE": "scan"})


async def test_handle_scan_aranet4_failure(listener, runner):
    """scan_aranet4 failure returns error."""
    runner.run_ephemeral = AsyncMock(return_value=False)

    command = Command(action="scan_aranet4", request_id="req-7")
    resp = await listener._handle_scan_aranet4(command)

    assert resp.status == "error"
    assert "failed" in resp.error.lower()


async def test_handle_discover_cameras(listener, runner, redis):
    """discover_cameras should run with MODE=discover and read results."""
    runner.run_ephemeral = AsyncMock(return_value=True)

    cameras = [{"name": "Camera 1", "host": "192.168.1.100", "port": 554}]
    await redis.set("scan:network_camera", json.dumps(cameras))

    command = Command(action="discover_cameras", request_id="req-8")
    resp = await listener._handle_discover_cameras(command)

    assert resp.status == "ok"
    assert len(resp.data["cameras"]) == 1
    assert resp.data["cameras"][0]["host"] == "192.168.1.100"
    runner.run_ephemeral.assert_awaited_once_with("source-camera", env={"MODE": "discover"})


async def test_handle_restart_service(listener, runner):
    """restart_service should stop then start the service."""
    runner.stop_service = AsyncMock(return_value=True)
    runner.start_service = AsyncMock(return_value=True)

    command = Command(
        action="restart_service", request_id="req-9", params={"service": "web-gateway"}
    )
    resp = await listener._handle_restart_service(command)

    assert resp.status == "ok"
    runner.stop_service.assert_awaited_once_with("web-gateway")
    runner.start_service.assert_awaited_once_with("web-gateway")


async def test_handle_restart_service_missing_param(listener):
    """restart_service without service parameter returns error."""
    command = Command(action="restart_service", request_id="req-10", params={})
    resp = await listener._handle_restart_service(command)

    assert resp.status == "error"
    assert "Missing" in resp.error


async def test_handle_unknown_command(listener, redis):
    """Unknown command should publish error response."""
    published = []
    original_publish = redis.publish

    async def track_publish(channel, data):
        published.append((channel, json.loads(data)))
        return await original_publish(channel, data)

    redis.publish = track_publish

    command = Command(action="unknown_action", request_id="req-11")
    await listener._handle_command(command)

    # Should publish error response
    assert len(published) == 1
    channel, data = published[0]
    assert "response" in channel
    assert data["status"] == "error"
    assert "Unknown" in data["error"]


async def test_response_published_to_correct_channel(listener, redis, runner):
    """Responses should be published to cmd:orchestrator:response:{request_id}."""
    runner.start_service = AsyncMock(return_value=True)
    published = []
    original_publish = redis.publish

    async def track_publish(channel, data):
        published.append((channel, data))
        return await original_publish(channel, data)

    redis.publish = track_publish

    command = Command(action="start_camera", request_id="my-request-123")
    await listener._handle_command(command)

    assert len(published) == 1
    channel, _ = published[0]
    assert channel == "cmd:orchestrator:response:my-request-123"
