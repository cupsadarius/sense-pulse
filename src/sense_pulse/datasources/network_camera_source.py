"""Network camera stream status data source implementation."""

from datetime import datetime

from sense_pulse.config import NetworkCameraConfig
from sense_pulse.datasources.base import DataSource, DataSourceMetadata, SensorReading
from sense_pulse.devices.network_camera import NetworkCameraDevice, StreamStatus
from sense_pulse.web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="network_camera")


class NetworkCameraDataSource(DataSource):
    """
    Network camera stream status data source.

    Reports the current status of the RTSP to HLS stream.
    """

    def __init__(self, config: NetworkCameraConfig, device: NetworkCameraDevice):
        """Initialize network camera data source."""
        self._config = config
        self._device = device

    async def initialize(self) -> None:
        """Initialize network camera data source."""
        if not self._config.enabled:
            logger.info("Network camera data source disabled")
            return

        # Device is started separately by CLI
        logger.info("Network camera data source initialized")

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
            status = self._device.get_status()

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
                "Network camera status fetched",
                status=status["status"],
                connected=status["camera"]["connected"],
            )

            return readings

        except Exception as e:
            logger.error("Error fetching network camera status", error=str(e))
            return []

    def get_metadata(self) -> DataSourceMetadata:
        """Get network camera data source metadata."""
        return DataSourceMetadata(
            source_id="network_camera",
            name="Network Camera",
            description="RTSP network camera stream status",
            refresh_interval=5,  # Check status every 5 seconds
            requires_auth=False,
            enabled=self._config.enabled,
        )

    async def health_check(self) -> bool:
        """Check if network camera stream is healthy."""
        if not self._config.enabled:
            return True  # Disabled is considered "healthy"

        try:
            return self._device.state.status == StreamStatus.STREAMING
        except Exception as e:
            logger.debug("Network camera health check failed", error=str(e))
            return False

    async def shutdown(self) -> None:
        """Clean up resources."""
        # Device shutdown is handled separately
        logger.debug("Network camera data source shut down")

    def get_device(self) -> NetworkCameraDevice:
        """Get the network camera device instance."""
        return self._device
