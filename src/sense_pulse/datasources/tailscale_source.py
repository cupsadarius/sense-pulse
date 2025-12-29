"""Tailscale data source implementation"""

import logging
from datetime import datetime

from ..config import TailscaleConfig
from ..tailscale import TailscaleStatus
from .base import DataSource, DataSourceMetadata, SensorReading

logger = logging.getLogger(__name__)


class TailscaleDataSource(DataSource):
    """
    Tailscale VPN status data source.

    Each fetch runs a fresh 'tailscale status' CLI command.
    """

    def __init__(self, config: TailscaleConfig):
        """
        Initialize Tailscale data source.

        Args:
            config: Tailscale configuration
        """
        self._config = config
        # Set cache_duration to 0 to ensure fresh data on each fetch
        self._status = TailscaleStatus(cache_duration=0)

    async def initialize(self) -> None:
        """Initialize Tailscale data source (no-op)"""
        logger.info("Tailscale data source initialized")

    async def fetch_readings(self) -> list[SensorReading]:
        """
        Fetch fresh Tailscale status by running CLI command.

        Returns:
            List of sensor readings (connected status, device count)
        """
        try:
            summary = await self._status.get_status_summary()
            now = datetime.now()

            return [
                SensorReading(
                    sensor_id="tailscale_connected",
                    value=summary["connected"],
                    unit=None,
                    timestamp=now,
                    metadata={"type": "boolean"},
                ),
                SensorReading(
                    sensor_id="tailscale_devices",
                    value=summary["device_count"],
                    unit="devices",
                    timestamp=now,
                ),
            ]

        except Exception as e:
            logger.error(f"Error fetching Tailscale readings: {e}")
            # Return empty readings on error
            return []

    def get_metadata(self) -> DataSourceMetadata:
        """Get Tailscale data source metadata"""
        return DataSourceMetadata(
            source_id="tailscale",
            name="Tailscale",
            description="VPN connection status and peer count",
            refresh_interval=30,
            requires_auth=False,
            enabled=True,  # Always try to check Tailscale
        )

    async def health_check(self) -> bool:
        """Check if Tailscale CLI is available and working"""
        try:
            summary = await self._status.get_status_summary()
            # Even if not connected, if we can run the command, it's healthy
            return summary is not None
        except Exception as e:
            logger.debug(f"Tailscale health check failed: {e}")
            return False

    async def shutdown(self) -> None:
        """Clean up resources (no-op for Tailscale)"""
        logger.debug("Tailscale data source shut down")
