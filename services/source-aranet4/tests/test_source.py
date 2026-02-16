"""Tests for Aranet4 ephemeral source."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest

from aranet4_svc.scanner import Aranet4Reading
from aranet4_svc.source import Aranet4Source


@pytest.fixture
def redis():
    """Create a fakeredis instance."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def source() -> Aranet4Source:
    return Aranet4Source()


def _make_reading(
    co2: int = 450,
    temperature: float = 22.1,
    humidity: int = 45,
    pressure: float = 1013.2,
    battery: int = 85,
    timestamp: float = 1708000000.0,
) -> Aranet4Reading:
    return Aranet4Reading(
        co2=co2,
        temperature=temperature,
        humidity=humidity,
        pressure=pressure,
        battery=battery,
        timestamp=timestamp,
    )


class TestAranet4Source:
    """Tests for Aranet4Source."""

    def test_source_id(self, source: Aranet4Source) -> None:
        assert source.source_id == "co2"

    def test_metadata(self, source: Aranet4Source) -> None:
        meta = source.metadata
        assert meta.source_id == "co2"
        assert meta.refresh_interval == 60
        assert meta.enabled is True

    async def test_poll_no_sensors_configured(self, source: Aranet4Source, redis) -> None:
        # No config in Redis = empty sensors list
        readings = await source.poll(redis)
        assert readings == []

    async def test_poll_with_empty_sensors_list(self, source: Aranet4Source, redis) -> None:
        await redis.set("config:aranet4", json.dumps({"sensors": [], "timeout": 10}))
        readings = await source.poll(redis)
        assert readings == []

    async def test_poll_produces_5_readings_per_sensor(self, source: Aranet4Source, redis) -> None:
        config = {
            "sensors": [{"label": "office", "mac": "AA:BB:CC:DD:EE:01"}],
            "timeout": 10,
        }
        await redis.set("config:aranet4", json.dumps(config))

        mock_scan_results = {
            "office": _make_reading(
                co2=500, temperature=23.5, humidity=50, pressure=1015.0, battery=90
            ),
        }

        with patch("aranet4_svc.source.Aranet4Scanner") as MockScanner:
            instance = MockScanner.return_value
            instance.scan = AsyncMock(return_value=mock_scan_results)
            readings = await source.poll(redis)

        assert len(readings) == 5

        # Verify sensor_ids match CONTRACT.md pattern
        sensor_ids = {r.sensor_id for r in readings}
        assert sensor_ids == {
            "office:co2",
            "office:temperature",
            "office:humidity",
            "office:pressure",
            "office:battery",
        }

        # Verify values and units
        by_id = {r.sensor_id: r for r in readings}
        assert by_id["office:co2"].value == 500
        assert by_id["office:co2"].unit == "ppm"
        assert by_id["office:temperature"].value == 23.5
        assert by_id["office:temperature"].unit == "C"
        assert by_id["office:humidity"].value == 50
        assert by_id["office:humidity"].unit == "%"
        assert by_id["office:pressure"].value == 1015.0
        assert by_id["office:pressure"].unit == "mbar"
        assert by_id["office:battery"].value == 90
        assert by_id["office:battery"].unit == "%"

    async def test_poll_multiple_sensors(self, source: Aranet4Source, redis) -> None:
        config = {
            "sensors": [
                {"label": "office", "mac": "AA:BB:CC:DD:EE:01"},
                {"label": "bedroom", "mac": "AA:BB:CC:DD:EE:02"},
            ],
            "timeout": 10,
        }
        await redis.set("config:aranet4", json.dumps(config))

        mock_scan_results = {
            "office": _make_reading(co2=450),
            "bedroom": _make_reading(co2=800),
        }

        with patch("aranet4_svc.source.Aranet4Scanner") as MockScanner:
            instance = MockScanner.return_value
            instance.scan = AsyncMock(return_value=mock_scan_results)
            readings = await source.poll(redis)

        assert len(readings) == 10  # 5 per sensor

        office_readings = [r for r in readings if r.sensor_id.startswith("office:")]
        bedroom_readings = [r for r in readings if r.sensor_id.startswith("bedroom:")]
        assert len(office_readings) == 5
        assert len(bedroom_readings) == 5

    async def test_poll_skips_missing_sensors(self, source: Aranet4Source, redis) -> None:
        config = {
            "sensors": [
                {"label": "office", "mac": "AA:BB:CC:DD:EE:01"},
                {"label": "bedroom", "mac": "AA:BB:CC:DD:EE:02"},
            ],
            "timeout": 10,
        }
        await redis.set("config:aranet4", json.dumps(config))

        mock_scan_results = {
            "office": _make_reading(),
            "bedroom": None,  # Not found in scan
        }

        with patch("aranet4_svc.source.Aranet4Scanner") as MockScanner:
            instance = MockScanner.return_value
            instance.scan = AsyncMock(return_value=mock_scan_results)
            readings = await source.poll(redis)

        assert len(readings) == 5  # Only office sensor
        sensor_ids = {r.sensor_id for r in readings}
        assert all(sid.startswith("office:") for sid in sensor_ids)

    async def test_poll_reads_config_from_redis(self, source: Aranet4Source, redis) -> None:
        config = {
            "sensors": [{"label": "office", "mac": "AA:BB:CC:DD:EE:01"}],
            "timeout": 15,
        }
        await redis.set("config:aranet4", json.dumps(config))

        with patch("aranet4_svc.source.Aranet4Scanner") as MockScanner:
            instance = MockScanner.return_value
            instance.scan = AsyncMock(return_value={"office": None})
            await source.poll(redis)

            # Verify scanner was called with correct timeout from config
            instance.scan.assert_called_once()
            call_kwargs = instance.scan.call_args
            assert call_kwargs.kwargs["timeout"] == 15


class TestAranet4ScanMode:
    """Tests for scan mode (discover devices -> write to Redis)."""

    async def test_scan_mode_writes_to_redis(self, redis) -> None:
        from aranet4_svc.main import SCAN_KEY, SCAN_TTL, run_scan_mode

        mock_devices = [
            {"name": "Aranet4 12345", "mac": "AA:BB:CC:DD:EE:01", "rssi": -50},
            {"name": "Aranet4 67890", "mac": "AA:BB:CC:DD:EE:02", "rssi": -70},
        ]

        with (
            patch("aranet4_svc.main.create_redis", return_value=redis),
            patch("aranet4_svc.main.read_config", return_value={"timeout": 10}),
            patch("aranet4_svc.main.Aranet4Scanner") as MockScanner,
        ):
            instance = MockScanner.return_value
            instance.discover = AsyncMock(return_value=mock_devices)
            await run_scan_mode()

        # Verify data was written to Redis
        stored = await redis.get(SCAN_KEY)
        assert stored is not None
        parsed = json.loads(stored)
        assert len(parsed) == 2
        assert parsed[0]["name"] == "Aranet4 12345"
        assert parsed[0]["mac"] == "AA:BB:CC:DD:EE:01"

        # Verify TTL was set
        ttl = await redis.ttl(SCAN_KEY)
        assert 0 < ttl <= SCAN_TTL

    async def test_scan_mode_empty_results(self, redis) -> None:
        from aranet4_svc.main import SCAN_KEY, run_scan_mode

        with (
            patch("aranet4_svc.main.create_redis", return_value=redis),
            patch("aranet4_svc.main.read_config", return_value=None),
            patch("aranet4_svc.main.Aranet4Scanner") as MockScanner,
        ):
            instance = MockScanner.return_value
            instance.discover = AsyncMock(return_value=[])
            await run_scan_mode()

        stored = await redis.get(SCAN_KEY)
        assert stored is not None
        assert json.loads(stored) == []
