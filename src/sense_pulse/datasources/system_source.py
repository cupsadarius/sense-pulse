"""System statistics data source implementation"""

from datetime import datetime

from ..devices.system import SystemStats
from ..web.log_handler import get_structured_logger
from .base import DataSource, DataSourceMetadata, SensorReading

logger = get_structured_logger(__name__, component="system")


class SystemStatsDataSource(DataSource):
    """
    System statistics data source.

    Each fetch reads fresh system metrics using psutil.
    """

    def __init__(self):
        """Initialize system stats data source"""
        self._stats = SystemStats()

    async def initialize(self) -> None:
        """Initialize system stats data source (no-op)"""
        logger.info("System stats data source initialized")

    async def fetch_readings(self) -> list[SensorReading]:
        """
        Fetch fresh system statistics.

        Returns:
            List of sensor readings (CPU, memory, load, temperature)
        """
        try:
            stats = await self._stats.get_stats()
            now = datetime.now()

            logger.debug(
                "System stats fetched",
                cpu_percent=stats["cpu_percent"],
                memory_percent=stats["memory_percent"],
                load_1min=round(stats["load_1min"], 2),
                cpu_temp=stats["cpu_temp"],
            )

            return [
                SensorReading(
                    sensor_id="cpu_percent",
                    value=stats["cpu_percent"],
                    unit="%",
                    timestamp=now,
                ),
                SensorReading(
                    sensor_id="memory_percent",
                    value=stats["memory_percent"],
                    unit="%",
                    timestamp=now,
                ),
                SensorReading(
                    sensor_id="load_1min",
                    value=stats["load_1min"],
                    unit="load",
                    timestamp=now,
                ),
                SensorReading(
                    sensor_id="cpu_temp",
                    value=stats["cpu_temp"],
                    unit="°C",
                    timestamp=now,
                ),
            ]

        except Exception as e:
            logger.error("Error fetching system stats readings", error=str(e))
            # Return empty readings on error
            return []

    def get_metadata(self) -> DataSourceMetadata:
        """Get system stats data source metadata"""
        return DataSourceMetadata(
            source_id="system",
            name="System Stats",
            description="CPU, memory, load, and temperature metrics",
            refresh_interval=30,
            requires_auth=False,
            enabled=True,
        )

    async def health_check(self) -> bool:
        """Check if system stats are available"""
        try:
            stats = await self._stats.get_stats()
            # If we get any non-zero values, system is healthy
            return any(v > 0 for v in stats.values())
        except Exception as e:
            logger.debug("System stats health check failed", error=str(e))
            return False

    async def shutdown(self) -> None:
        """Clean up resources (no-op for system stats)"""
        logger.debug("System stats data source shut down")
