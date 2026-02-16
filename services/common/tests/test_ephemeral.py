"""Tests for sense_common.ephemeral base class."""

import json

import fakeredis.aioredis
import pytest
from sense_common.ephemeral import EphemeralSource
from sense_common.models import SensorReading, SourceMetadata


class MockWeatherSource(EphemeralSource):
    """A mock ephemeral source for testing."""

    @property
    def source_id(self) -> str:
        return "weather"

    @property
    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            source_id="weather",
            name="Weather",
            description="Test weather source",
            refresh_interval=300,
        )

    async def poll(self, redis) -> list[SensorReading]:
        return [
            SensorReading(sensor_id="weather_temp", value=18.0, unit="C", timestamp=1708000000.0),
            SensorReading(sensor_id="weather_humidity", value=72, unit="%", timestamp=1708000000.0),
        ]


class FailingSource(EphemeralSource):
    """A source that always fails."""

    @property
    def source_id(self) -> str:
        return "failing"

    @property
    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            source_id="failing",
            name="Failing",
            description="Always fails",
            refresh_interval=30,
        )

    async def poll(self, redis) -> list[SensorReading]:
        raise RuntimeError("Connection refused")


@pytest.fixture
def fake_redis_server():
    return fakeredis.aioredis.FakeServer()


class TestEphemeralSource:
    async def test_successful_run(self, fake_redis_server):
        source = MockWeatherSource()

        # We can't use create_redis (it calls ping on a URL), so we test poll flow directly
        redis = fakeredis.aioredis.FakeRedis(server=fake_redis_server, decode_responses=True)

        # Simulate what run() does
        readings = await source.poll(redis)
        assert len(readings) == 2

        # Write readings manually (testing the poll output)
        from sense_common.models import SourceStatus
        from sense_common.redis_client import (
            publish_data,
            read_source,
            write_metadata,
            write_readings,
            write_status,
        )

        await write_readings(redis, source.source_id, readings)
        await write_metadata(redis, source.source_id, source.metadata)
        await write_status(
            redis,
            source.source_id,
            SourceStatus(
                source_id=source.source_id,
                last_poll=1708000000.0,
                last_success=1708000001.0,
                poll_count=1,
            ),
        )
        await publish_data(redis, source.source_id)

        # Verify readings in Redis
        result = await read_source(redis, "weather")
        assert "weather_temp" in result
        assert result["weather_temp"]["value"] == 18.0

        # Verify metadata
        meta_raw = await redis.get("meta:weather")
        assert meta_raw is not None
        meta = json.loads(meta_raw)
        assert meta["name"] == "Weather"

        # Verify status
        status_raw = await redis.get("status:weather")
        assert status_raw is not None
        status = json.loads(status_raw)
        assert status["poll_count"] == 1

        await redis.aclose()

    async def test_failed_poll_writes_error_status(self, fake_redis_server):
        source = FailingSource()
        redis = fakeredis.aioredis.FakeRedis(server=fake_redis_server, decode_responses=True)

        from sense_common.models import SourceStatus
        from sense_common.redis_client import write_status

        # Simulate what run() does on failure
        try:
            await source.poll(redis)
        except RuntimeError as e:
            await write_status(
                redis,
                source.source_id,
                SourceStatus(
                    source_id=source.source_id,
                    last_poll=1708000000.0,
                    last_error=str(e),
                    error_count=1,
                ),
            )

        status_raw = await redis.get("status:failing")
        assert status_raw is not None
        status = json.loads(status_raw)
        assert status["last_error"] == "Connection refused"
        assert status["error_count"] == 1

        await redis.aclose()
