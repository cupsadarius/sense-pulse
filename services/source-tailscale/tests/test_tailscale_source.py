"""Tests for Tailscale source."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tailscale.source import TailscaleSource

SAMPLE_TS_CONNECTED = {
    "BackendState": "Running",
    "Self": {
        "ID": "abc123",
        "HostName": "myhost",
        "Online": True,
    },
    "Peer": {
        "peer1": {"HostName": "device1", "Online": True},
        "peer2": {"HostName": "device2", "Online": True},
        "peer3": {"HostName": "device3", "Online": False},
    },
}

SAMPLE_TS_DISCONNECTED = {
    "BackendState": "Stopped",
    "Self": None,
    "Peer": {},
}


@pytest.fixture
def source() -> TailscaleSource:
    return TailscaleSource()


def _make_process_mock(
    stdout: bytes = b"",
    returncode: int = 0,
) -> MagicMock:
    """Create a mock subprocess with communicate."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, b""))
    return proc


class TestTailscaleSourceProperties:
    def test_source_id(self, source: TailscaleSource) -> None:
        assert source.source_id == "tailscale"

    def test_metadata(self, source: TailscaleSource) -> None:
        meta = source.metadata
        assert meta.source_id == "tailscale"
        assert meta.name == "Tailscale"
        assert meta.refresh_interval == 30


class TestTailscalePoll:
    async def test_connected_state(self, source: TailscaleSource) -> None:
        """Connected Tailscale returns connected=True and device_count=2."""
        redis_mock = AsyncMock()
        proc = _make_process_mock(json.dumps(SAMPLE_TS_CONNECTED).encode())

        with patch("tailscale.source.asyncio.create_subprocess_exec", return_value=proc):
            readings = await source.poll(redis_mock)

        assert len(readings) == 2
        by_id = {r.sensor_id: r for r in readings}

        assert by_id["connected"].value is True
        assert by_id["connected"].unit is None
        assert by_id["device_count"].value == 2  # 2 online peers
        assert by_id["device_count"].unit == "devices"

    async def test_disconnected_state(self, source: TailscaleSource) -> None:
        """Disconnected Tailscale returns connected=False and device_count=0."""
        redis_mock = AsyncMock()
        proc = _make_process_mock(json.dumps(SAMPLE_TS_DISCONNECTED).encode())

        with patch("tailscale.source.asyncio.create_subprocess_exec", return_value=proc):
            readings = await source.poll(redis_mock)

        assert len(readings) == 2
        by_id = {r.sensor_id: r for r in readings}
        assert by_id["connected"].value is False
        assert by_id["device_count"].value == 0

    async def test_nonzero_returncode(self, source: TailscaleSource) -> None:
        """Non-zero return code returns connected=False, device_count=0."""
        redis_mock = AsyncMock()
        proc = _make_process_mock(b"", returncode=1)

        with patch("tailscale.source.asyncio.create_subprocess_exec", return_value=proc):
            readings = await source.poll(redis_mock)

        assert len(readings) == 2
        by_id = {r.sensor_id: r for r in readings}
        assert by_id["connected"].value is False
        assert by_id["device_count"].value == 0

    async def test_file_not_found(self, source: TailscaleSource) -> None:
        """Tailscale not installed returns empty list."""
        redis_mock = AsyncMock()

        with patch(
            "tailscale.source.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("tailscale not found"),
        ):
            readings = await source.poll(redis_mock)

        assert readings == []

    async def test_timeout(self, source: TailscaleSource) -> None:
        """Timeout returns empty list."""
        redis_mock = AsyncMock()
        proc = MagicMock()
        proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)

        with (
            patch("tailscale.source.asyncio.create_subprocess_exec", return_value=proc),
            patch("tailscale.source.asyncio.wait_for", side_effect=asyncio.TimeoutError),
        ):
            readings = await source.poll(redis_mock)

        assert readings == []

    async def test_json_parse_error(self, source: TailscaleSource) -> None:
        """Invalid JSON returns empty list."""
        redis_mock = AsyncMock()
        proc = _make_process_mock(b"not json")

        with patch("tailscale.source.asyncio.create_subprocess_exec", return_value=proc):
            readings = await source.poll(redis_mock)

        assert readings == []

    async def test_sensor_ids_match_contract(self, source: TailscaleSource) -> None:
        """Verify sensor_ids match CONTRACT.md."""
        redis_mock = AsyncMock()
        proc = _make_process_mock(json.dumps(SAMPLE_TS_CONNECTED).encode())

        with patch("tailscale.source.asyncio.create_subprocess_exec", return_value=proc):
            readings = await source.poll(redis_mock)

        sensor_ids = {r.sensor_id for r in readings}
        assert sensor_ids == {"connected", "device_count"}


class TestTailscaleFullRun:
    async def test_run_writes_to_redis(self, source: TailscaleSource) -> None:
        """Integration test: run() writes readings to fakeredis."""
        fakeredis = pytest.importorskip("fakeredis")
        fake = fakeredis.aioredis.FakeRedis(decode_responses=True)

        proc = _make_process_mock(json.dumps(SAMPLE_TS_CONNECTED).encode())

        with (
            patch("tailscale.source.asyncio.create_subprocess_exec", return_value=proc),
            patch("sense_common.ephemeral.create_redis", return_value=fake),
        ):
            await source.run("redis://fake:6379")

        val = await fake.get("source:tailscale:connected")
        assert val is not None
        data = json.loads(val)
        assert data["value"] is True

        val = await fake.get("source:tailscale:device_count")
        assert val is not None
        data = json.loads(val)
        assert data["value"] == 2
        assert data["unit"] == "devices"

        meta = await fake.get("meta:tailscale")
        assert meta is not None

        status = await fake.get("status:tailscale")
        assert status is not None

        await fake.aclose()
