"""Pi-hole data source implementation"""

import logging
from datetime import datetime

from ..config import PiholeConfig
from ..pihole import PiHoleStats
from .base import DataSource, DataSourceMetadata, SensorReading

logger = logging.getLogger(__name__)


class PiHoleDataSource(DataSource):
    """
    Pi-hole statistics data source.

    Each fetch makes a fresh HTTP request to the Pi-hole API.
    """

    def __init__(self, config: PiholeConfig):
        """
        Initialize Pi-hole data source.

        Args:
            config: Pi-hole configuration
        """
        self._config = config
        self._stats = PiHoleStats(config.host, config.password)
        self._enabled = bool(config.host)

    async def initialize(self) -> None:
        """Authenticate with Pi-hole on startup"""
        if self._enabled and self._config.password:
            try:
                await self._stats._authenticate()
                logger.info("Pi-hole data source initialized successfully")
            except Exception as e:
                logger.warning(f"Pi-hole authentication failed during init: {e}")
                # Don't fail initialization - we'll retry on first fetch

    async def fetch_readings(self) -> list[SensorReading]:
        """
        Fetch fresh statistics from Pi-hole API.

        Returns:
            List of sensor readings (queries, blocked, percentage)
        """
        if not self._enabled:
            logger.debug("Pi-hole data source is disabled")
            return []

        try:
            summary = await self._stats.get_summary()
            now = datetime.now()

            return [
                SensorReading(
                    sensor_id="queries_today",
                    value=summary["queries_today"],
                    unit="queries",
                    timestamp=now,
                ),
                SensorReading(
                    sensor_id="ads_blocked_today",
                    value=summary["ads_blocked_today"],
                    unit="ads",
                    timestamp=now,
                ),
                SensorReading(
                    sensor_id="ads_percentage_today",
                    value=summary["ads_percentage_today"],
                    unit="%",
                    timestamp=now,
                ),
            ]

        except Exception as e:
            logger.error(f"Error fetching Pi-hole readings: {e}")
            # Return empty readings on error - cache will use last known good data
            return []

    def get_metadata(self) -> DataSourceMetadata:
        """Get Pi-hole data source metadata"""
        return DataSourceMetadata(
            source_id="pihole",
            name="Pi-hole",
            description=f"Network-wide ad blocking statistics from {self._config.host}",
            refresh_interval=30,
            requires_auth=bool(self._config.password),
            enabled=self._enabled,
        )

    async def health_check(self) -> bool:
        """Check if Pi-hole is reachable"""
        if not self._enabled:
            return False

        try:
            await self._stats.get_summary()
            return True
        except Exception as e:
            logger.debug(f"Pi-hole health check failed: {e}")
            return False

    async def shutdown(self) -> None:
        """Close HTTP client"""
        await self._stats.close()
        logger.debug("Pi-hole data source shut down")
