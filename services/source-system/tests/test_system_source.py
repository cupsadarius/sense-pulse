"""Tests for system metrics source."""

from __future__ import annotations

import json
from collections import namedtuple
from unittest.mock import AsyncMock, patch

import pytest
from sense_common.models import SensorReading
from system.source import SystemSource

STemp = namedtuple("STemp", ["label", "current", "high", "critical"])


@pytest.fixture
def source() -> SystemSource:
    return SystemSource()


class TestSystemSourceProperties:
    def test_source_id(self, source: SystemSource) -> None:
        assert source.source_id == "system"

    def test_metadata(self, source: SystemSource) -> None:
        meta = source.metadata
        assert meta.source_id == "system"
        assert meta.name == "System Stats"
        assert meta.refresh_interval == 30


class TestSystemPoll:
    async def test_poll_returns_4_readings(self, source: SystemSource) -> None:
        """Successful poll returns 4 readings."""
        redis_mock = AsyncMock()

        vmem = type("vmem", (), {"percent": 61.2})()

        with (
            patch("system.source.psutil.cpu_percent", return_value=23.5),
            patch("system.source.psutil.virtual_memory", return_value=vmem),
            patch("system.source.os.getloadavg", return_value=(1.23, 0.9, 0.7)),
            patch(
                "system.source.psutil.sensors_temperatures",
                return_value={"cpu_thermal": [STemp("", 52.3, 80.0, 90.0)]},
                create=True,
            ),
        ):
            readings = await source.poll(redis_mock)

        assert len(readings) == 4
        assert all(isinstance(r, SensorReading) for r in readings)

    async def test_sensor_ids_match_contract(self, source: SystemSource) -> None:
        """Verify sensor_ids match CONTRACT.md."""
        redis_mock = AsyncMock()

        vmem = type("vmem", (), {"percent": 61.2})()

        with (
            patch("system.source.psutil.cpu_percent", return_value=23.5),
            patch("system.source.psutil.virtual_memory", return_value=vmem),
            patch("system.source.os.getloadavg", return_value=(1.23, 0.9, 0.7)),
            patch(
                "system.source.psutil.sensors_temperatures",
                return_value={"cpu_thermal": [STemp("", 52.3, 80.0, 90.0)]},
                create=True,
            ),
        ):
            readings = await source.poll(redis_mock)

        sensor_ids = {r.sensor_id for r in readings}
        assert sensor_ids == {"cpu_percent", "memory_percent", "load_1min", "cpu_temp"}

    async def test_values_and_units(self, source: SystemSource) -> None:
        """Verify values and units from CONTRACT.md."""
        redis_mock = AsyncMock()

        vmem = type("vmem", (), {"percent": 61.2})()

        with (
            patch("system.source.psutil.cpu_percent", return_value=23.5),
            patch("system.source.psutil.virtual_memory", return_value=vmem),
            patch("system.source.os.getloadavg", return_value=(1.23, 0.9, 0.7)),
            patch(
                "system.source.psutil.sensors_temperatures",
                return_value={"cpu_thermal": [STemp("", 52.3, 80.0, 90.0)]},
                create=True,
            ),
        ):
            readings = await source.poll(redis_mock)

        by_id = {r.sensor_id: r for r in readings}

        assert by_id["cpu_percent"].value == 23.5
        assert by_id["cpu_percent"].unit == "%"
        assert by_id["memory_percent"].value == 61.2
        assert by_id["memory_percent"].unit == "%"
        assert by_id["load_1min"].value == 1.23
        assert by_id["load_1min"].unit == "load"
        assert by_id["cpu_temp"].value == 52.3
        assert by_id["cpu_temp"].unit == "C"

    async def test_coretemp_fallback(self, source: SystemSource) -> None:
        """Uses coretemp if cpu_thermal is not available."""
        redis_mock = AsyncMock()

        vmem = type("vmem", (), {"percent": 50.0})()

        with (
            patch("system.source.psutil.cpu_percent", return_value=10.0),
            patch("system.source.psutil.virtual_memory", return_value=vmem),
            patch("system.source.os.getloadavg", return_value=(0.5, 0.4, 0.3)),
            patch(
                "system.source.psutil.sensors_temperatures",
                return_value={"coretemp": [STemp("Core 0", 45.0, 80.0, 90.0)]},
                create=True,
            ),
        ):
            readings = await source.poll(redis_mock)

        by_id = {r.sensor_id: r for r in readings}
        assert by_id["cpu_temp"].value == 45.0

    async def test_no_temperature_sensors(self, source: SystemSource) -> None:
        """Missing temperature sensors returns 0.0."""
        redis_mock = AsyncMock()

        vmem = type("vmem", (), {"percent": 50.0})()

        with (
            patch("system.source.psutil.cpu_percent", return_value=10.0),
            patch("system.source.psutil.virtual_memory", return_value=vmem),
            patch("system.source.os.getloadavg", return_value=(0.5, 0.4, 0.3)),
            patch("system.source.psutil.sensors_temperatures", return_value={}, create=True),
        ):
            readings = await source.poll(redis_mock)

        by_id = {r.sensor_id: r for r in readings}
        assert by_id["cpu_temp"].value == 0.0

    async def test_sensors_temperatures_raises(self, source: SystemSource) -> None:
        """sensors_temperatures raising an exception still returns 0.0 for cpu_temp."""
        redis_mock = AsyncMock()

        vmem = type("vmem", (), {"percent": 50.0})()

        with (
            patch("system.source.psutil.cpu_percent", return_value=10.0),
            patch("system.source.psutil.virtual_memory", return_value=vmem),
            patch("system.source.os.getloadavg", return_value=(0.5, 0.4, 0.3)),
            patch(
                "system.source.psutil.sensors_temperatures",
                side_effect=AttributeError("not supported"),
                create=True,
            ),
        ):
            readings = await source.poll(redis_mock)

        by_id = {r.sensor_id: r for r in readings}
        assert by_id["cpu_temp"].value == 0.0

    async def test_containerized_host_proc(self, source: SystemSource) -> None:
        """Sets HOST_PROC when /host/proc exists."""
        redis_mock = AsyncMock()

        vmem = type("vmem", (), {"percent": 50.0})()

        with (
            patch("system.source.os.path.isdir", return_value=True),
            patch("system.source.os.environ", {}) as env,
            patch("system.source.psutil.cpu_percent", return_value=10.0),
            patch("system.source.psutil.virtual_memory", return_value=vmem),
            patch("system.source.os.getloadavg", return_value=(0.5, 0.4, 0.3)),
            patch("system.source.psutil.sensors_temperatures", return_value={}, create=True),
        ):
            await source.poll(redis_mock)
            assert env.get("HOST_PROC") == "/host/proc"


class TestSystemFullRun:
    async def test_run_writes_to_redis(self, source: SystemSource) -> None:
        """Integration test: run() writes readings to fakeredis."""
        fakeredis = pytest.importorskip("fakeredis")
        fake = fakeredis.aioredis.FakeRedis(decode_responses=True)

        vmem = type("vmem", (), {"percent": 61.2})()

        with (
            patch("system.source.psutil.cpu_percent", return_value=23.5),
            patch("system.source.psutil.virtual_memory", return_value=vmem),
            patch("system.source.os.getloadavg", return_value=(1.23, 0.9, 0.7)),
            patch(
                "system.source.psutil.sensors_temperatures",
                return_value={"cpu_thermal": [STemp("", 52.3, 80.0, 90.0)]},
                create=True,
            ),
            patch("sense_common.ephemeral.create_redis", return_value=fake),
        ):
            await source.run("redis://fake:6379")

        val = await fake.get("source:system:cpu_percent")
        assert val is not None
        data = json.loads(val)
        assert data["value"] == 23.5
        assert data["unit"] == "%"

        val = await fake.get("source:system:cpu_temp")
        assert val is not None
        data = json.loads(val)
        assert data["value"] == 52.3
        assert data["unit"] == "C"

        meta = await fake.get("meta:system")
        assert meta is not None

        status = await fake.get("status:system")
        assert status is not None

        await fake.aclose()
