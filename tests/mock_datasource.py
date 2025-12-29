"""Mock data source for testing"""

from datetime import datetime
from typing import Optional

from sense_pulse.datasources.base import DataSource, DataSourceMetadata, SensorReading


class MockDataSource(DataSource):
    """
    Mock data source for testing.

    This can be configured to return any data and simulate various conditions.
    """

    def __init__(
        self,
        source_id: str = "mock",
        name: str = "Mock Source",
        readings: Optional[list[SensorReading]] = None,
        fail_on_initialize: bool = False,
        fail_on_fetch: bool = False,
        fail_on_health_check: bool = False,
        enabled: bool = True,
    ):
        """
        Initialize mock data source.

        Args:
            source_id: Unique source identifier
            name: Human-readable name
            readings: List of readings to return (or None for default)
            fail_on_initialize: Raise exception on initialize()
            fail_on_fetch: Raise exception on fetch_readings()
            fail_on_health_check: Return False on health_check()
            enabled: Whether source is enabled
        """
        self._source_id = source_id
        self._name = name
        self._readings = readings or [
            SensorReading(
                sensor_id=f"{source_id}_test",
                value=42,
                unit="units",
                timestamp=datetime.now(),
            )
        ]
        self._fail_on_initialize = fail_on_initialize
        self._fail_on_fetch = fail_on_fetch
        self._fail_on_health_check = fail_on_health_check
        self._enabled = enabled
        self._initialized = False
        self._fetch_count = 0
        self._shutdown_called = False

    async def initialize(self) -> None:
        """Initialize the mock data source"""
        if self._fail_on_initialize:
            raise RuntimeError("Mock initialization failure")
        self._initialized = True

    async def fetch_readings(self) -> list[SensorReading]:
        """Return configured mock readings"""
        if self._fail_on_fetch:
            raise RuntimeError("Mock fetch failure")
        self._fetch_count += 1
        return self._readings.copy()

    def get_metadata(self) -> DataSourceMetadata:
        """Return mock metadata"""
        return DataSourceMetadata(
            source_id=self._source_id,
            name=self._name,
            description=f"Mock data source for testing ({self._source_id})",
            refresh_interval=30,
            requires_auth=False,
            enabled=self._enabled,
        )

    async def health_check(self) -> bool:
        """Return configured health status"""
        if self._fail_on_health_check:
            return False
        return self._initialized

    async def shutdown(self) -> None:
        """Mark as shut down"""
        self._shutdown_called = True

    # Test helper methods

    def set_readings(self, readings: list[SensorReading]) -> None:
        """Update the readings that will be returned"""
        self._readings = readings

    def get_fetch_count(self) -> int:
        """Get number of times fetch_readings was called"""
        return self._fetch_count

    def is_initialized(self) -> bool:
        """Check if initialize was called"""
        return self._initialized

    def is_shutdown(self) -> bool:
        """Check if shutdown was called"""
        return self._shutdown_called
