"""Tests for sense_common.redis_client using fakeredis."""

import asyncio
import json

import fakeredis.aioredis
import pytest

from sense_common.models import (
    Command,
    CommandResponse,
    SensorReading,
    SourceMetadata,
    SourceStatus,
)
from sense_common.redis_client import (
    publish_command,
    publish_config_changed,
    publish_data,
    publish_response,
    read_all_sources,
    read_all_statuses,
    read_config,
    read_source,
    read_status,
    seed_config_from_env,
    subscribe_commands,
    subscribe_config_changes,
    write_config,
    write_metadata,
    write_readings,
    write_status,
)


@pytest.fixture
def redis():
    """Create a fakeredis instance."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


class TestWriteReadReadings:
    async def test_write_and_read_source(self, redis):
        readings = [
            SensorReading(sensor_id="temperature", value=24.3, unit="C", timestamp=1708000000.0),
            SensorReading(sensor_id="humidity", value=45.2, unit="%", timestamp=1708000000.0),
        ]
        await write_readings(redis, "sensors", readings)

        result = await read_source(redis, "sensors")
        assert "temperature" in result
        assert result["temperature"]["value"] == 24.3
        assert result["temperature"]["unit"] == "C"
        assert "humidity" in result
        assert result["humidity"]["value"] == 45.2

    async def test_write_readings_ttl(self, redis):
        readings = [SensorReading(sensor_id="temp", value=20, timestamp=1708000000.0)]
        await write_readings(redis, "test", readings, ttl=60)

        ttl = await redis.ttl("source:test:temp")
        assert 0 < ttl <= 60

    async def test_read_source_empty(self, redis):
        result = await read_source(redis, "nonexistent")
        assert result == {}

    async def test_read_all_sources(self, redis):
        await write_readings(
            redis,
            "tailscale",
            [
                SensorReading(sensor_id="connected", value=True, timestamp=1708000000.0),
                SensorReading(
                    sensor_id="device_count", value=5, unit="devices", timestamp=1708000000.0
                ),
            ],
        )
        await write_readings(
            redis,
            "pihole",
            [
                SensorReading(
                    sensor_id="queries_today", value=12345, unit="queries", timestamp=1708000000.0
                ),
            ],
        )

        result = await read_all_sources(redis)
        assert "tailscale" in result
        assert "pihole" in result
        assert result["tailscale"]["connected"]["value"] is True
        assert result["pihole"]["queries_today"]["value"] == 12345

    async def test_read_all_sources_empty(self, redis):
        result = await read_all_sources(redis)
        assert result == {}


class TestMetadata:
    async def test_write_and_read_metadata(self, redis):
        meta = SourceMetadata(
            source_id="weather",
            name="Weather",
            description="Current weather from wttr.in",
            refresh_interval=300,
        )
        await write_metadata(redis, "weather", meta)

        # Verify it persists (no TTL)
        ttl = await redis.ttl("meta:weather")
        assert ttl == -1  # -1 means no expiry


class TestStatus:
    async def test_write_and_read_status(self, redis):
        status = SourceStatus(
            source_id="pihole",
            last_poll=1708000000.0,
            last_success=1708000000.0,
            poll_count=42,
        )
        await write_status(redis, "pihole", status)

        result = await read_status(redis, "pihole")
        assert result is not None
        assert result.source_id == "pihole"
        assert result.poll_count == 42

    async def test_status_ttl(self, redis):
        status = SourceStatus(source_id="test")
        await write_status(redis, "test", status, ttl=120)

        ttl = await redis.ttl("status:test")
        assert 0 < ttl <= 120

    async def test_read_all_statuses(self, redis):
        await write_status(redis, "a", SourceStatus(source_id="a", poll_count=1))
        await write_status(redis, "b", SourceStatus(source_id="b", poll_count=2))

        statuses = await read_all_statuses(redis)
        ids = {s.source_id for s in statuses}
        assert ids == {"a", "b"}

    async def test_read_status_missing(self, redis):
        result = await read_status(redis, "nonexistent")
        assert result is None


class TestPubSubData:
    async def test_publish_data(self, redis):
        pubsub = redis.pubsub()
        await pubsub.subscribe("data:weather")

        # Consume the subscribe confirmation
        msg = await pubsub.get_message(timeout=1)
        assert msg["type"] == "subscribe"

        await publish_data(redis, "weather")

        msg = await pubsub.get_message(timeout=1)
        assert msg is not None
        assert msg["type"] == "message"
        payload = json.loads(msg["data"])
        assert payload["source_id"] == "weather"
        assert "timestamp" in payload

        await pubsub.unsubscribe()
        await pubsub.aclose()


class TestPubSubCommands:
    async def test_publish_and_subscribe_commands(self, redis):
        cmd = Command(action="clear", request_id="test-123")
        received: list[Command] = []

        async def listener():
            async for c in subscribe_commands(redis, "sensors"):
                received.append(c)
                break  # exit after first command

        task = asyncio.create_task(listener())
        await asyncio.sleep(0.05)  # let subscriber connect

        await publish_command(redis, "sensors", cmd)
        await asyncio.wait_for(task, timeout=2)

        assert len(received) == 1
        assert received[0].action == "clear"
        assert received[0].request_id == "test-123"


class TestPubSubResponses:
    async def test_publish_and_wait_response(self, redis):
        response = CommandResponse(
            request_id="resp-123",
            status="ok",
            data={"message": "done"},
        )

        async def publisher():
            await asyncio.sleep(0.05)
            await publish_response(redis, "sensors", response)

        task = asyncio.create_task(publisher())
        result = await wait_response_helper(redis, "sensors", "resp-123", timeout=2)
        await task

        assert result is not None
        assert result.status == "ok"
        assert result.data["message"] == "done"


async def wait_response_helper(redis, source_id, request_id, timeout):
    """Helper that uses the wait_response function."""
    from sense_common.redis_client import wait_response

    return await wait_response(redis, source_id, request_id, timeout=timeout)


class TestConfig:
    async def test_write_and_read_config(self, redis):
        await write_config(redis, "weather", {"location": "London"})

        result = await read_config(redis, "weather")
        assert result == {"location": "London"}

    async def test_read_config_missing(self, redis):
        result = await read_config(redis, "nonexistent")
        assert result is None

    async def test_seed_config_nx(self, redis):
        # First seed should succeed
        result = await seed_config_from_env(redis, "weather", {"location": "London"})
        assert result is True

        # Second seed should NOT overwrite
        result = await seed_config_from_env(redis, "weather", {"location": "Paris"})
        assert result is False

        # Value should still be London
        config = await read_config(redis, "weather")
        assert config["location"] == "London"

    async def test_config_no_ttl(self, redis):
        await write_config(redis, "test", {"key": "value"})
        ttl = await redis.ttl("config:test")
        assert ttl == -1  # no expiry


class TestConfigChanges:
    async def test_subscribe_config_changes(self, redis):
        received: list[str] = []

        async def listener():
            async for section in subscribe_config_changes(redis):
                received.append(section)
                break

        task = asyncio.create_task(listener())
        await asyncio.sleep(0.05)

        await publish_config_changed(redis, "display")
        await asyncio.wait_for(task, timeout=2)

        assert received == ["display"]
