"""Tests for Pi-hole source."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from pihole.source import PiHoleSource
from sense_common.models import SensorReading

SAMPLE_STATS_RESPONSE = {
    "queries": {
        "total": 12345,
        "blocked": 1234,
        "percent_blocked": 10.0,
    }
}

SAMPLE_AUTH_RESPONSE = {
    "session": {
        "valid": True,
        "sid": "test-session-id",
    }
}


@pytest.fixture
def source() -> PiHoleSource:
    return PiHoleSource()


class TestPiHoleSourceProperties:
    def test_source_id(self, source: PiHoleSource) -> None:
        assert source.source_id == "pihole"

    def test_metadata(self, source: PiHoleSource) -> None:
        meta = source.metadata
        assert meta.source_id == "pihole"
        assert meta.name == "Pi-hole"
        assert meta.refresh_interval == 30

    def test_metadata_enabled(self, source: PiHoleSource) -> None:
        assert source.metadata.enabled is True


class TestPiHolePoll:
    async def test_poll_returns_3_readings(self, source: PiHoleSource) -> None:
        """Successful poll returns 3 readings."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(
            return_value=json.dumps({"host": "http://pihole.local", "password": "secret"})
        )

        auth_response = httpx.Response(
            200,
            json=SAMPLE_AUTH_RESPONSE,
            request=httpx.Request("POST", "http://pihole.local/api/auth"),
        )
        stats_response = httpx.Response(
            200,
            json=SAMPLE_STATS_RESPONSE,
            request=httpx.Request("GET", "http://pihole.local/api/stats/summary"),
        )

        with patch("pihole.source.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=auth_response)
            mock_client.get = AsyncMock(return_value=stats_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            readings = await source.poll(redis_mock)

        assert len(readings) == 3
        assert all(isinstance(r, SensorReading) for r in readings)

    async def test_sensor_ids_match_contract(self, source: PiHoleSource) -> None:
        """Verify sensor_ids match CONTRACT.md."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(
            return_value=json.dumps({"host": "http://pihole.local", "password": "secret"})
        )

        auth_response = httpx.Response(
            200,
            json=SAMPLE_AUTH_RESPONSE,
            request=httpx.Request("POST", "http://pihole.local/api/auth"),
        )
        stats_response = httpx.Response(
            200,
            json=SAMPLE_STATS_RESPONSE,
            request=httpx.Request("GET", "http://pihole.local/api/stats/summary"),
        )

        with patch("pihole.source.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=auth_response)
            mock_client.get = AsyncMock(return_value=stats_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            readings = await source.poll(redis_mock)

        by_id = {r.sensor_id: r for r in readings}
        assert "queries_today" in by_id
        assert "ads_blocked_today" in by_id
        assert "ads_percentage_today" in by_id

    async def test_values_and_units(self, source: PiHoleSource) -> None:
        """Verify values and units match CONTRACT.md."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(
            return_value=json.dumps({"host": "http://pihole.local", "password": "secret"})
        )

        auth_response = httpx.Response(
            200,
            json=SAMPLE_AUTH_RESPONSE,
            request=httpx.Request("POST", "http://pihole.local/api/auth"),
        )
        stats_response = httpx.Response(
            200,
            json=SAMPLE_STATS_RESPONSE,
            request=httpx.Request("GET", "http://pihole.local/api/stats/summary"),
        )

        with patch("pihole.source.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=auth_response)
            mock_client.get = AsyncMock(return_value=stats_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            readings = await source.poll(redis_mock)

        by_id = {r.sensor_id: r for r in readings}
        assert by_id["queries_today"].value == 12345
        assert by_id["queries_today"].unit == "queries"
        assert by_id["ads_blocked_today"].value == 1234
        assert by_id["ads_blocked_today"].unit == "ads"
        assert by_id["ads_percentage_today"].value == 10.0
        assert by_id["ads_percentage_today"].unit == "%"

    async def test_no_host_returns_empty(self, source: PiHoleSource) -> None:
        """No configured host returns empty list."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)

        readings = await source.poll(redis_mock)
        assert readings == []

    async def test_no_password_skips_auth(self, source: PiHoleSource) -> None:
        """No password skips authentication."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=json.dumps({"host": "http://pihole.local"}))

        stats_response = httpx.Response(
            200,
            json=SAMPLE_STATS_RESPONSE,
            request=httpx.Request("GET", "http://pihole.local/api/stats/summary"),
        )

        with patch("pihole.source.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock()  # Should not be called
            mock_client.get = AsyncMock(return_value=stats_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            readings = await source.poll(redis_mock)

        assert len(readings) == 3
        mock_client.post.assert_not_called()

    async def test_stats_fetch_failure_returns_empty(self, source: PiHoleSource) -> None:
        """When fetch_stats returns None, poll returns empty."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(
            return_value=json.dumps({"host": "http://pihole.local", "password": "secret"})
        )

        auth_response = httpx.Response(
            200,
            json={"session": {"valid": False}},
            request=httpx.Request("POST", "http://pihole.local/api/auth"),
        )

        with patch("pihole.source.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=auth_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            readings = await source.poll(redis_mock)

        assert readings == []

    async def test_env_fallback_for_host(self, source: PiHoleSource) -> None:
        """Falls back to PIHOLE_HOST env var when Redis config is empty."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)

        stats_response = httpx.Response(
            200,
            json=SAMPLE_STATS_RESPONSE,
            request=httpx.Request("GET", "http://env-pihole.local/api/stats/summary"),
        )

        with (
            patch.dict(
                "os.environ",
                {"PIHOLE_HOST": "http://env-pihole.local", "PIHOLE_PASSWORD": ""},
            ),
            patch("pihole.source.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=stats_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            readings = await source.poll(redis_mock)

        assert len(readings) == 3


class TestPiHoleFullRun:
    async def test_run_writes_to_redis(self, source: PiHoleSource) -> None:
        """Integration test: run() writes readings to fakeredis."""
        fakeredis = pytest.importorskip("fakeredis")
        fake = fakeredis.aioredis.FakeRedis(decode_responses=True)

        await fake.set(
            "config:pihole",
            json.dumps({"host": "http://pihole.local", "password": "secret"}),
        )

        auth_response = httpx.Response(
            200,
            json=SAMPLE_AUTH_RESPONSE,
            request=httpx.Request("POST", "http://pihole.local/api/auth"),
        )
        stats_response = httpx.Response(
            200,
            json=SAMPLE_STATS_RESPONSE,
            request=httpx.Request("GET", "http://pihole.local/api/stats/summary"),
        )

        with (
            patch("pihole.source.httpx.AsyncClient") as mock_client_cls,
            patch("sense_common.ephemeral.create_redis", return_value=fake),
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=auth_response)
            mock_client.get = AsyncMock(return_value=stats_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await source.run("redis://fake:6379")

        val = await fake.get("source:pihole:queries_today")
        assert val is not None
        data = json.loads(val)
        assert data["value"] == 12345
        assert data["unit"] == "queries"

        meta = await fake.get("meta:pihole")
        assert meta is not None

        status = await fake.get("status:pihole")
        assert status is not None

        await fake.aclose()
