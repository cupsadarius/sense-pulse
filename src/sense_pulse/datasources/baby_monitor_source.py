"""Baby monitor stream status data source implementation."""

from datetime import datetime

from sense_pulse.baby_monitor import StreamManager, StreamStatus
from sense_pulse.config import BabyMonitorConfig
from sense_pulse.datasources.base import DataSource, DataSourceMetadata, SensorReading
from sense_pulse.web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="baby_monitor")


class BabyMonitorDataSource(DataSource):
    """
    Baby monitor stream status data source.

    Reports the current status of the RTSP to HLS stream.
    """

    def __init__(self, config: BabyMonitorConfig, stream_manager: StreamManager):
        """Initialize baby monitor data source."""
        self._config = config
        self._stream_manager = stream_manager

    async def initialize(self) -> None:
        """Initialize baby monitor data source."""
        if not self._config.enabled:
            logger.info("Baby monitor data source disabled")
            return

        # Stream manager is started separately by CLI
        logger.info("Baby monitor data source initialized")

    async def fetch_readings(self) -> list[SensorReading]:
        """
        Fetch current stream status.

        Returns:
            List of sensor readings representing stream status
        """
        if not self._config.enabled:
            return []

        try:
            now = datetime.now()
            status = self._stream_manager.get_status()

            readings = [
                SensorReading(
                    sensor_id="stream_status",
                    value=status["status"],
                    unit=None,
                    timestamp=now,
                    metadata={
                        "connected": status["camera"]["connected"],
                        "error": status["error"],
                    },
                ),
                SensorReading(
                    sensor_id="stream_uptime",
                    value=status["uptime_seconds"],
                    unit="seconds",
                    timestamp=now,
                ),
            ]

            # Add resolution and fps if available
            if status["camera"]["resolution"]:
                readings.append(
                    SensorReading(
                        sensor_id="stream_resolution",
                        value=status["camera"]["resolution"],
                        unit=None,
                        timestamp=now,
                    )
                )

            if status["camera"]["fps"]:
                readings.append(
                    SensorReading(
                        sensor_id="stream_fps",
                        value=status["camera"]["fps"],
                        unit="fps",
                        timestamp=now,
                    )
                )

            logger.debug(
                "Baby monitor status fetched",
                status=status["status"],
                connected=status["camera"]["connected"],
            )

            return readings

        except Exception as e:
            logger.error("Error fetching baby monitor status", error=str(e))
            return []

    def get_metadata(self) -> DataSourceMetadata:
        """Get baby monitor data source metadata."""
        return DataSourceMetadata(
            source_id="baby_monitor",
            name="Baby Monitor",
            description="RTSP baby camera stream status",
            refresh_interval=5,  # Check status every 5 seconds
            requires_auth=False,
            enabled=self._config.enabled,
        )

    async def health_check(self) -> bool:
        """Check if baby monitor stream is healthy."""
        if not self._config.enabled:
            return True  # Disabled is considered "healthy"

        try:
            return self._stream_manager.state.status == StreamStatus.STREAMING
        except Exception as e:
            logger.debug("Baby monitor health check failed", error=str(e))
            return False

    async def shutdown(self) -> None:
        """Clean up resources."""
        # Stream manager shutdown is handled separately
        logger.debug("Baby monitor data source shut down")

    def get_stream_manager(self) -> StreamManager:
        """Get the stream manager instance."""
        return self._stream_manager
