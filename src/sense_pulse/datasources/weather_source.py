"""Weather data source implementation using wttr.io API"""

from datetime import datetime

import httpx

from ..config import WeatherConfig
from ..web.log_handler import get_structured_logger
from .base import DataSource, DataSourceMetadata, SensorReading

logger = get_structured_logger(__name__, component="weather")


class WeatherDataSource(DataSource):
    """
    Weather data source using wttr.in API.

    Fetches current weather conditions for a configured location.
    Data is cached by the cache layer based on cache_duration config.
    """

    def __init__(self, config: WeatherConfig):
        """
        Initialize weather data source.

        Args:
            config: Weather configuration with location
        """
        self._config = config
        self._client: httpx.AsyncClient | None = None
        self._last_data: dict = {}
        self._cache_until: datetime | None = None

    async def initialize(self) -> None:
        """Initialize HTTP client for weather API"""
        self._client = httpx.AsyncClient(timeout=10.0)
        logger.info(
            "Weather data source initialized",
            location=self._config.location or "auto",
        )

    async def fetch_readings(self) -> list[SensorReading]:
        """
        Fetch current weather data from wttr.in API.

        Returns:
            List of sensor readings (temperature, conditions, humidity, etc.)
        """
        if not self._config.enabled:
            logger.debug("Weather data source is disabled")
            return []

        if not self._config.location:
            logger.debug("Weather location not configured")
            return []

        # Check internal cache (wttr.in updates hourly, no need to spam API)
        now = datetime.now()
        if self._cache_until and now < self._cache_until and self._last_data:
            logger.debug("Using cached weather data")
            return self._create_readings_from_data(self._last_data, now)

        try:
            if not self._client:
                logger.error("HTTP client not initialized")
                return []

            # Fetch weather data from wttr.in
            # Format: j1 gives JSON with current conditions and forecast
            url = f"https://wttr.in/{self._config.location}?format=j1"
            logger.info("Fetching weather", location=self._config.location, url=url)

            response = await self._client.get(url)
            response.raise_for_status()
            data = response.json()

            # Cache the data
            self._last_data = data
            from datetime import timedelta

            self._cache_until = now + timedelta(seconds=self._config.cache_duration)

            return self._create_readings_from_data(data, now)

        except httpx.TimeoutException:
            logger.warning("Weather API timeout", location=self._config.location)
            return self._fallback_readings(now)
        except httpx.HTTPError as e:
            logger.error("Weather API HTTP error", error=str(e))
            return self._fallback_readings(now)
        except Exception as e:
            logger.error("Error fetching weather data", error=str(e))
            return self._fallback_readings(now)

    def _create_readings_from_data(self, data: dict, timestamp: datetime) -> list[SensorReading]:
        """
        Create sensor readings from wttr.in API response.

        Args:
            data: JSON response from wttr.in
            timestamp: Timestamp for the readings

        Returns:
            List of sensor readings
        """
        try:
            current = data.get("current_condition", [{}])[0]
            nearest = data.get("nearest_area", [{}])[0]

            # Extract location info
            area = nearest.get("areaName", [{}])[0].get("value", "Unknown")
            country = nearest.get("country", [{}])[0].get("value", "")

            # Extract current conditions
            temp_c = float(current.get("temp_C", 0))
            feels_like_c = float(current.get("FeelsLikeC", temp_c))
            humidity = int(current.get("humidity", 0))
            weather_desc = current.get("weatherDesc", [{}])[0].get("value", "Unknown")
            wind_speed_kmph = float(current.get("windspeedKmph", 0))
            wind_dir = current.get("winddir16Point", "N")
            pressure_mb = float(current.get("pressure", 0))
            uv_index = int(current.get("uvIndex", 0))
            visibility_km = float(current.get("visibility", 0))
            cloud_cover = int(current.get("cloudcover", 0))

            readings = [
                SensorReading(
                    sensor_id="weather_temp",
                    value=temp_c,
                    unit="°C",
                    timestamp=timestamp,
                ),
                SensorReading(
                    sensor_id="weather_feels_like",
                    value=feels_like_c,
                    unit="°C",
                    timestamp=timestamp,
                ),
                SensorReading(
                    sensor_id="weather_humidity",
                    value=humidity,
                    unit="%",
                    timestamp=timestamp,
                ),
                SensorReading(
                    sensor_id="weather_conditions",
                    value=weather_desc,
                    unit=None,
                    timestamp=timestamp,
                ),
                SensorReading(
                    sensor_id="weather_wind",
                    value=wind_speed_kmph,
                    unit="km/h",
                    timestamp=timestamp,
                ),
                SensorReading(
                    sensor_id="weather_wind_dir",
                    value=wind_dir,
                    unit=None,
                    timestamp=timestamp,
                ),
                SensorReading(
                    sensor_id="weather_pressure",
                    value=pressure_mb,
                    unit="mb",
                    timestamp=timestamp,
                ),
                SensorReading(
                    sensor_id="weather_uv_index",
                    value=uv_index,
                    unit=None,
                    timestamp=timestamp,
                ),
                SensorReading(
                    sensor_id="weather_visibility",
                    value=visibility_km,
                    unit="km",
                    timestamp=timestamp,
                ),
                SensorReading(
                    sensor_id="weather_cloud_cover",
                    value=cloud_cover,
                    unit="%",
                    timestamp=timestamp,
                ),
                SensorReading(
                    sensor_id="weather_location",
                    value=f"{area}, {country}" if country else area,
                    unit=None,
                    timestamp=timestamp,
                ),
            ]

            # Add 3-day forecast data
            forecast_data = data.get("weather", [])
            if forecast_data:
                forecast_list = []
                for day in forecast_data[:3]:  # Only 3 days
                    date = day.get("date", "")
                    max_temp = float(day.get("maxtempC", 0))
                    min_temp = float(day.get("mintempC", 0))
                    avg_temp = float(day.get("avgtempC", 0))
                    # Get description from hourly data (midday forecast)
                    hourly = day.get("hourly", [])
                    desc = "Unknown"
                    if len(hourly) >= 4:  # Get midday forecast (12:00)
                        desc = hourly[4].get("weatherDesc", [{}])[0].get("value", "Unknown")

                    forecast_list.append(
                        {
                            "date": date,
                            "max_temp": max_temp,
                            "min_temp": min_temp,
                            "avg_temp": avg_temp,
                            "description": desc,
                        }
                    )

                # Store forecast as a single sensor reading with JSON data
                readings.append(
                    SensorReading(
                        sensor_id="weather_forecast",
                        value=forecast_list,
                        unit=None,
                        timestamp=timestamp,
                    )
                )

            return readings

        except (KeyError, IndexError, ValueError, TypeError) as e:
            logger.error(f"Error parsing weather data: {e}")
            return self._fallback_readings(timestamp)

    def _fallback_readings(self, timestamp: datetime) -> list[SensorReading]:
        """
        Return fallback readings when API fails.

        Args:
            timestamp: Timestamp for the readings

        Returns:
            List of sensor readings with N/A values
        """
        if self._last_data:
            # Return last successful data if available
            return self._create_readings_from_data(self._last_data, timestamp)

        # Return empty readings to indicate unavailable
        return [
            SensorReading(
                sensor_id="weather_conditions",
                value="Unavailable",
                unit=None,
                timestamp=timestamp,
            )
        ]

    def get_metadata(self) -> DataSourceMetadata:
        """Get weather data source metadata"""
        return DataSourceMetadata(
            source_id="weather",
            name="Weather",
            description=f"Current weather conditions from wttr.in ({self._config.location or 'auto'})",
            refresh_interval=self._config.cache_duration,
            requires_auth=False,
            enabled=self._config.enabled,
        )

    async def health_check(self) -> bool:
        """Check if weather API is reachable"""
        if not self._config.enabled or not self._config.location:
            return False

        try:
            if not self._client:
                return False

            # Quick check with minimal format
            url = f"https://wttr.in/{self._config.location}?format=%t"
            response = await self._client.get(url, timeout=5.0)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Weather health check failed: {e}")
            return False

    async def shutdown(self) -> None:
        """Clean up HTTP client"""
        if self._client:
            await self._client.aclose()
            logger.debug("Weather data source shut down")
