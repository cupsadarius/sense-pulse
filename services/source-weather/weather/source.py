"""Weather data source using wttr.in API."""

from __future__ import annotations

import logging

import httpx
from sense_common.config import get_config_value
from sense_common.ephemeral import EphemeralSource
from sense_common.models import SensorReading, SourceMetadata
from sense_common.redis_client import read_config

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class WeatherSource(EphemeralSource):
    """Ephemeral source that fetches weather data from wttr.in."""

    @property
    def source_id(self) -> str:
        return "weather"

    @property
    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            source_id="weather",
            name="Weather",
            description="Current weather conditions from wttr.in",
            refresh_interval=300,
        )

    async def poll(self, redis: aioredis.Redis) -> list[SensorReading]:
        """Fetch weather data and return 26 scalar readings."""
        config = await read_config(redis, "weather")
        location = get_config_value(config, "WEATHER_LOCATION", default="")

        if not location:
            logger.warning("No weather location configured")
            return []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"https://wttr.in/{location}?format=j1"
                logger.info("Fetching weather for %s", location)
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException:
            logger.warning("Weather API timeout for %s", location)
            return []
        except httpx.HTTPError as e:
            logger.error("Weather API HTTP error: %s", e)
            return []
        except Exception as e:
            logger.error("Weather API error: %s", e)
            return []

        return self._parse_response(data, location)

    def _parse_response(self, data: dict, location: str) -> list[SensorReading]:
        """Parse wttr.in JSON response into 26 SensorReading objects."""
        try:
            current = data.get("current_condition", [{}])[0]
            nearest = data.get("nearest_area", [{}])[0]

            area = nearest.get("areaName", [{}])[0].get("value", "Unknown")
            country = nearest.get("country", [{}])[0].get("value", "")
            location_str = f"{area}, {country}" if country else area

            readings: list[SensorReading] = [
                SensorReading(
                    sensor_id="weather_temp",
                    value=float(current.get("temp_C", 0)),
                    unit="C",
                ),
                SensorReading(
                    sensor_id="weather_feels_like",
                    value=float(current.get("FeelsLikeC", 0)),
                    unit="C",
                ),
                SensorReading(
                    sensor_id="weather_humidity",
                    value=int(current.get("humidity", 0)),
                    unit="%",
                ),
                SensorReading(
                    sensor_id="weather_conditions",
                    value=current.get("weatherDesc", [{}])[0].get("value", "Unknown"),
                    unit=None,
                ),
                SensorReading(
                    sensor_id="weather_wind",
                    value=float(current.get("windspeedKmph", 0)),
                    unit="km/h",
                ),
                SensorReading(
                    sensor_id="weather_wind_dir",
                    value=current.get("winddir16Point", "N"),
                    unit=None,
                ),
                SensorReading(
                    sensor_id="weather_pressure",
                    value=float(current.get("pressure", 0)),
                    unit="mb",
                ),
                SensorReading(
                    sensor_id="weather_uv_index",
                    value=int(current.get("uvIndex", 0)),
                    unit=None,
                ),
                SensorReading(
                    sensor_id="weather_visibility",
                    value=float(current.get("visibility", 0)),
                    unit="km",
                ),
                SensorReading(
                    sensor_id="weather_cloud_cover",
                    value=int(current.get("cloudcover", 0)),
                    unit="%",
                ),
                SensorReading(
                    sensor_id="weather_location",
                    value=location_str,
                    unit=None,
                ),
            ]

            # 3-day forecast: 5 readings per day = 15 readings
            forecast_data = data.get("weather", [])
            for i, day in enumerate(forecast_data[:3]):
                prefix = f"forecast_d{i}"
                date = day.get("date", "")
                max_temp = float(day.get("maxtempC", 0))
                min_temp = float(day.get("mintempC", 0))
                avg_temp = float(day.get("avgtempC", 0))

                # Get description from midday hourly forecast
                hourly = day.get("hourly", [])
                desc = "Unknown"
                if len(hourly) > 4:
                    desc = hourly[4].get("weatherDesc", [{}])[0].get("value", "Unknown")

                readings.extend(
                    [
                        SensorReading(sensor_id=f"{prefix}_date", value=date, unit=None),
                        SensorReading(sensor_id=f"{prefix}_max_temp", value=max_temp, unit="C"),
                        SensorReading(sensor_id=f"{prefix}_min_temp", value=min_temp, unit="C"),
                        SensorReading(sensor_id=f"{prefix}_avg_temp", value=avg_temp, unit="C"),
                        SensorReading(sensor_id=f"{prefix}_description", value=desc, unit=None),
                    ]
                )

            return readings

        except (KeyError, IndexError, ValueError, TypeError) as e:
            logger.error("Error parsing weather data: %s", e)
            return []
