"""Tests for sense_common.models."""

import time

from sense_common.models import (
    Command,
    CommandResponse,
    SensorReading,
    SourceMetadata,
    SourceStatus,
)


class TestSensorReading:
    def test_basic_creation(self):
        r = SensorReading(sensor_id="temperature", value=24.3, unit="C")
        assert r.sensor_id == "temperature"
        assert r.value == 24.3
        assert r.unit == "C"
        assert isinstance(r.timestamp, float)

    def test_serialization_roundtrip(self):
        r = SensorReading(sensor_id="connected", value=True, unit=None, timestamp=1708000000.0)
        data = r.model_dump_json()
        r2 = SensorReading.model_validate_json(data)
        assert r2.sensor_id == r.sensor_id
        assert r2.value == r.value
        assert r2.unit == r.unit
        assert r2.timestamp == r.timestamp

    def test_scalar_types(self):
        # int
        r = SensorReading(sensor_id="count", value=42)
        assert r.value == 42
        # float
        r = SensorReading(sensor_id="temp", value=22.5)
        assert r.value == 22.5
        # str
        r = SensorReading(sensor_id="status", value="ok")
        assert r.value == "ok"
        # bool
        r = SensorReading(sensor_id="connected", value=True)
        assert r.value is True

    def test_default_timestamp(self):
        before = time.time()
        r = SensorReading(sensor_id="test", value=1)
        after = time.time()
        assert before <= r.timestamp <= after


class TestSourceMetadata:
    def test_creation(self):
        m = SourceMetadata(
            source_id="weather",
            name="Weather",
            description="Weather from wttr.in",
            refresh_interval=300,
        )
        assert m.source_id == "weather"
        assert m.enabled is True

    def test_disabled(self):
        m = SourceMetadata(
            source_id="test",
            name="Test",
            description="Test source",
            refresh_interval=30,
            enabled=False,
        )
        assert m.enabled is False


class TestSourceStatus:
    def test_default_values(self):
        s = SourceStatus(source_id="test")
        assert s.last_poll is None
        assert s.last_success is None
        assert s.last_error is None
        assert s.poll_count == 0
        assert s.error_count == 0

    def test_with_error(self):
        s = SourceStatus(
            source_id="test",
            last_poll=1708000000.0,
            last_error="Connection refused",
            error_count=3,
        )
        assert s.last_error == "Connection refused"
        assert s.error_count == 3

    def test_serialization_roundtrip(self):
        s = SourceStatus(
            source_id="pihole",
            last_poll=1708000000.0,
            last_success=1708000000.0,
            poll_count=42,
        )
        data = s.model_dump_json()
        s2 = SourceStatus.model_validate_json(data)
        assert s2.source_id == s.source_id
        assert s2.poll_count == s.poll_count


class TestCommand:
    def test_default_request_id(self):
        c = Command(action="clear")
        assert c.request_id  # not empty
        assert len(c.request_id) > 10  # UUID-like

    def test_unique_request_ids(self):
        c1 = Command(action="clear")
        c2 = Command(action="clear")
        assert c1.request_id != c2.request_id

    def test_with_params(self):
        c = Command(action="set_rotation", params={"rotation": 180})
        assert c.params["rotation"] == 180

    def test_default_timestamp(self):
        before = time.time()
        c = Command(action="test")
        after = time.time()
        assert before <= c.timestamp <= after


class TestCommandResponse:
    def test_ok_response(self):
        r = CommandResponse(request_id="abc-123", status="ok")
        assert r.status == "ok"
        assert r.error is None
        assert r.data == {}

    def test_error_response(self):
        r = CommandResponse(
            request_id="abc-123",
            status="error",
            error="Something went wrong",
        )
        assert r.status == "error"
        assert r.error == "Something went wrong"

    def test_with_data(self):
        r = CommandResponse(
            request_id="abc-123",
            status="ok",
            data={"devices": [{"name": "Aranet4"}]},
        )
        assert r.data["devices"][0]["name"] == "Aranet4"
