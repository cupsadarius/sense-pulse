"""Tests for sense_common.persistent base class."""

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
    read_source,
    write_readings,
)


class MockPersistentSource:
    """A mock persistent source for testing poll/command/config behavior."""

    def __init__(self):
        self.source_id = "sensors"
        self.metadata = SourceMetadata(
            source_id="sensors",
            name="Sensors",
            description="Test sensor source",
            refresh_interval=30,
        )
        self.poll_count = 0
        self.commands_received: list[Command] = []
        self.config_changes: list[str] = []

    async def poll(self, redis) -> list[SensorReading]:
        self.poll_count += 1
        return [
            SensorReading(sensor_id="temperature", value=24.3, unit="C", timestamp=1708000000.0),
        ]

    async def handle_command(self, command: Command) -> CommandResponse:
        self.commands_received.append(command)
        return CommandResponse(request_id=command.request_id, status="ok")

    async def on_config_changed(self, redis, section: str) -> None:
        self.config_changes.append(section)


@pytest.fixture
def fake_redis_server():
    return fakeredis.aioredis.FakeServer()


@pytest.fixture
def redis(fake_redis_server):
    return fakeredis.aioredis.FakeRedis(server=fake_redis_server, decode_responses=True)


class TestPollLoop:
    async def test_poll_produces_readings(self, redis):
        source = MockPersistentSource()
        readings = await source.poll(redis)
        assert len(readings) == 1
        assert readings[0].sensor_id == "temperature"
        assert source.poll_count == 1

    async def test_poll_writes_to_redis(self, redis):
        source = MockPersistentSource()
        readings = await source.poll(redis)
        await write_readings(redis, source.source_id, readings)

        result = await read_source(redis, "sensors")
        assert "temperature" in result
        assert result["temperature"]["value"] == 24.3


class TestCommandHandling:
    async def test_handle_command(self):
        source = MockPersistentSource()
        cmd = Command(action="clear", request_id="test-cmd-1")
        response = await source.handle_command(cmd)

        assert response.status == "ok"
        assert response.request_id == "test-cmd-1"
        assert len(source.commands_received) == 1
        assert source.commands_received[0].action == "clear"


class TestConfigChanges:
    async def test_config_change_handler(self, redis):
        source = MockPersistentSource()
        await source.on_config_changed(redis, "display")

        assert source.config_changes == ["display"]
