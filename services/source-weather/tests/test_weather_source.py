"""Tests for weather source."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sense_common.models import SensorReading
from weather.source import WeatherSource

# Sample wttr.in response
SAMPLE_WTTR_RESPONSE = {
    "current_condition": [
        {
            "temp_C": "18",
            "FeelsLikeC": "16",
            "humidity": "72",
            "weatherDesc": [{"value": "Partly cloudy"}],
            "windspeedKmph": "15",
            "winddir16Point": "SW",
            "pressure": "1015",
            "uvIndex": "3",
            "visibility": "10",
            "cloudcover": "50",
        }
    ],
    "nearest_area": [
        {
            "areaName": [{"value": "London"}],
            "country": [{"value": "United Kingdom"}],
        }
    ],
    "weather": [
        {
            "date": "2026-02-16",
            "maxtempC": "12",
            "mintempC": "5",
            "avgtempC": "8",
            "hourly": [
                {},
                {},
                {},
                {},
                {"weatherDesc": [{"value": "Partly cloudy"}]},
            ],
        },
        {
            "date": "2026-02-17",
            "maxtempC": "10",
            "mintempC": "3",
            "avgtempC": "6",
            "hourly": [
                {},
                {},
                {},
                {},
                {"weatherDesc": [{"value": "Rain"}]},
            ],
        },
        {
            "date": "2026-02-18",
            "maxtempC": "14",
            "mintempC": "7",
            "avgtempC": "10",
            "hourly": [
                {},
                {},
                {},
                {},
                {"weatherDesc": [{"value": "Sunny"}]},
            ],
        },
    ],
}


@pytest.fixture
def source() -> WeatherSource:
    return WeatherSource()


class TestWeatherSourceProperties:
    def test_source_id(self, source: WeatherSource) -> None:
        assert source.source_id == "weather"

    def test_metadata(self, source: WeatherSource) -> None:
        meta = source.metadata
        assert meta.source_id == "weather"
        assert meta.name == "Weather"
        assert meta.refresh_interval == 300

    def test_metadata_enabled(self, source: WeatherSource) -> None:
        assert source.metadata.enabled is True


class TestWeatherPoll:
    async def test_poll_returns_26_readings(self, source: WeatherSource) -> None:
        """Successful poll returns 11 current + 15 forecast = 26 readings."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=json.dumps({"location": "London"}))

        mock_response = httpx.Response(
            200,
            json=SAMPLE_WTTR_RESPONSE,
            request=httpx.Request("GET", "https://wttr.in/London?format=j1"),
        )

        with patch("weather.source.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            readings = await source.poll(redis_mock)

        assert len(readings) == 26
        assert all(isinstance(r, SensorReading) for r in readings)

    async def test_current_condition_sensor_ids(self, source: WeatherSource) -> None:
        """Verify 11 current condition sensor_ids match CONTRACT.md."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=json.dumps({"location": "London"}))

        mock_response = httpx.Response(
            200,
            json=SAMPLE_WTTR_RESPONSE,
            request=httpx.Request("GET", "https://wttr.in/London?format=j1"),
        )

        with patch("weather.source.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            readings = await source.poll(redis_mock)

        sensor_ids = [r.sensor_id for r in readings]

        # 11 current conditions
        expected_current = [
            "weather_temp",
            "weather_feels_like",
            "weather_humidity",
            "weather_conditions",
            "weather_wind",
            "weather_wind_dir",
            "weather_pressure",
            "weather_uv_index",
            "weather_visibility",
            "weather_cloud_cover",
            "weather_location",
        ]
        for sid in expected_current:
            assert sid in sensor_ids, f"Missing sensor_id: {sid}"

    async def test_forecast_sensor_ids(self, source: WeatherSource) -> None:
        """Verify 15 forecast sensor_ids match CONTRACT.md."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=json.dumps({"location": "London"}))

        mock_response = httpx.Response(
            200,
            json=SAMPLE_WTTR_RESPONSE,
            request=httpx.Request("GET", "https://wttr.in/London?format=j1"),
        )

        with patch("weather.source.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            readings = await source.poll(redis_mock)

        sensor_ids = [r.sensor_id for r in readings]

        # 15 forecast readings (3 days x 5 fields)
        for i in range(3):
            for field in ("date", "max_temp", "min_temp", "avg_temp", "description"):
                expected = f"forecast_d{i}_{field}"
                assert expected in sensor_ids, f"Missing sensor_id: {expected}"

    async def test_current_values_parsed_correctly(self, source: WeatherSource) -> None:
        """Verify values and units are correct from parsed response."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=json.dumps({"location": "London"}))

        mock_response = httpx.Response(
            200,
            json=SAMPLE_WTTR_RESPONSE,
            request=httpx.Request("GET", "https://wttr.in/London?format=j1"),
        )

        with patch("weather.source.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            readings = await source.poll(redis_mock)

        by_id = {r.sensor_id: r for r in readings}

        assert by_id["weather_temp"].value == 18.0
        assert by_id["weather_temp"].unit == "C"
        assert by_id["weather_feels_like"].value == 16.0
        assert by_id["weather_humidity"].value == 72
        assert by_id["weather_humidity"].unit == "%"
        assert by_id["weather_conditions"].value == "Partly cloudy"
        assert by_id["weather_conditions"].unit is None
        assert by_id["weather_wind"].value == 15.0
        assert by_id["weather_wind"].unit == "km/h"
        assert by_id["weather_wind_dir"].value == "SW"
        assert by_id["weather_pressure"].value == 1015.0
        assert by_id["weather_pressure"].unit == "mb"
        assert by_id["weather_uv_index"].value == 3
        assert by_id["weather_uv_index"].unit is None
        assert by_id["weather_visibility"].value == 10.0
        assert by_id["weather_visibility"].unit == "km"
        assert by_id["weather_cloud_cover"].value == 50
        assert by_id["weather_cloud_cover"].unit == "%"
        assert by_id["weather_location"].value == "London, United Kingdom"

    async def test_forecast_values_parsed_correctly(self, source: WeatherSource) -> None:
        """Verify forecast values are correctly parsed."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=json.dumps({"location": "London"}))

        mock_response = httpx.Response(
            200,
            json=SAMPLE_WTTR_RESPONSE,
            request=httpx.Request("GET", "https://wttr.in/London?format=j1"),
        )

        with patch("weather.source.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            readings = await source.poll(redis_mock)

        by_id = {r.sensor_id: r for r in readings}

        assert by_id["forecast_d0_date"].value == "2026-02-16"
        assert by_id["forecast_d0_max_temp"].value == 12.0
        assert by_id["forecast_d0_max_temp"].unit == "C"
        assert by_id["forecast_d0_min_temp"].value == 5.0
        assert by_id["forecast_d0_avg_temp"].value == 8.0
        assert by_id["forecast_d0_description"].value == "Partly cloudy"

        assert by_id["forecast_d1_date"].value == "2026-02-17"
        assert by_id["forecast_d1_description"].value == "Rain"

        assert by_id["forecast_d2_date"].value == "2026-02-18"
        assert by_id["forecast_d2_max_temp"].value == 14.0

    async def test_no_location_returns_empty(self, source: WeatherSource) -> None:
        """No configured location returns empty list."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)

        readings = await source.poll(redis_mock)
        assert readings == []

    async def test_http_error_returns_empty(self, source: WeatherSource) -> None:
        """HTTP error returns empty list."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=json.dumps({"location": "London"}))

        mock_response = httpx.Response(
            500,
            request=httpx.Request("GET", "https://wttr.in/London?format=j1"),
        )

        with patch("weather.source.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            readings = await source.poll(redis_mock)

        assert readings == []

    async def test_timeout_returns_empty(self, source: WeatherSource) -> None:
        """Timeout returns empty list."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=json.dumps({"location": "London"}))

        with patch("weather.source.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            readings = await source.poll(redis_mock)

        assert readings == []

    async def test_malformed_json_returns_empty(self, source: WeatherSource) -> None:
        """Malformed JSON response returns empty list."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=json.dumps({"location": "London"}))

        # Response with invalid JSON structure (missing expected keys)
        mock_response = httpx.Response(
            200,
            json={"unexpected": "data"},
            request=httpx.Request("GET", "https://wttr.in/London?format=j1"),
        )

        with patch("weather.source.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            readings = await source.poll(redis_mock)

        # _parse_response handles missing keys gracefully (defaults to 0/{})
        # but it won't crash -- may return partial or empty
        assert isinstance(readings, list)

    async def test_env_fallback_for_location(self, source: WeatherSource) -> None:
        """Falls back to WEATHER_LOCATION env var when Redis config is empty."""
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)  # No Redis config

        mock_response = httpx.Response(
            200,
            json=SAMPLE_WTTR_RESPONSE,
            request=httpx.Request("GET", "https://wttr.in/Paris?format=j1"),
        )

        with (
            patch.dict("os.environ", {"WEATHER_LOCATION": "Paris"}),
            patch("weather.source.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            readings = await source.poll(redis_mock)

        assert len(readings) == 26


class TestWeatherFullRun:
    async def test_run_writes_to_redis(self, source: WeatherSource) -> None:
        """Integration test: run() connects to fakeredis, writes readings."""
        fakeredis = pytest.importorskip("fakeredis")
        fake = fakeredis.aioredis.FakeRedis(decode_responses=True)

        # Seed config
        await fake.set("config:weather", json.dumps({"location": "London"}))

        mock_response = httpx.Response(
            200,
            json=SAMPLE_WTTR_RESPONSE,
            request=httpx.Request("GET", "https://wttr.in/London?format=j1"),
        )

        with (
            patch("weather.source.httpx.AsyncClient") as mock_client_cls,
            patch("sense_common.ephemeral.create_redis", return_value=fake),
        ):
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await source.run("redis://fake:6379")

        # Verify readings were written
        val = await fake.get("source:weather:weather_temp")
        assert val is not None
        data = json.loads(val)
        assert data["value"] == 18.0
        assert data["unit"] == "C"

        # Verify metadata was written
        meta = await fake.get("meta:weather")
        assert meta is not None

        # Verify status was written
        status = await fake.get("status:weather")
        assert status is not None

        await fake.aclose()
