"""
Base interface for all data sources in sense-pulse.

Data sources are responsible for fetching fresh data from sensors, APIs, or system sources.
They do NOT cache data - the cache layer handles caching by polling data sources periodically.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SensorReading:
    """
    A single sensor reading with metadata.

    Attributes:
        sensor_id: Unique identifier for this sensor (e.g., "co2", "pihole_queries")
        value: The actual sensor value
        unit: Optional unit of measurement (e.g., "ppm", "°C", "%")
        timestamp: When this reading was taken
        metadata: Additional context about the reading
    """

    sensor_id: str
    value: Any
    unit: str | None
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DataSourceMetadata:
    """
    Metadata describing a data source.

    Attributes:
        source_id: Unique identifier for this data source
        name: Human-readable name
        description: Brief description of what this source provides
        refresh_interval: How often (in seconds) the cache should poll this source
        requires_auth: Whether this source needs authentication
        enabled: Whether this source is currently enabled
    """

    source_id: str
    name: str
    description: str
    refresh_interval: int
    requires_auth: bool = False
    enabled: bool = True


class DataSource(ABC):
    """
    Abstract base class for all data sources.

    Data sources fetch fresh data from external sources (sensors, APIs, system).
    They should NOT implement their own caching - the Cache layer handles that
    by calling fetch_readings() periodically.

    For expensive operations (like BLE scans), a data source MAY maintain its own
    background polling mechanism, but fetch_readings() should return the latest
    available data without blocking for long operations.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the data source.

        This is called once at startup and should:
        - Establish connections
        - Authenticate if needed
        - Start background tasks (for expensive operations like BLE scanning)
        - Validate configuration

        Raises:
            Exception: If initialization fails
        """
        pass

    @abstractmethod
    async def fetch_readings(self) -> list[SensorReading]:
        """
        Fetch fresh readings from this data source.

        This method is called by the Cache layer every refresh_interval seconds.
        It should return current data from the source.

        For quick operations (HTTP, system calls): Make a fresh request/call.
        For slow operations (BLE scans): Return latest from background poller.

        Returns:
            List of sensor readings with current values

        Raises:
            Exception: If fetching data fails
        """
        pass

    @abstractmethod
    def get_metadata(self) -> DataSourceMetadata:
        """
        Get metadata about this data source.

        This is a synchronous method that returns configuration/metadata
        without performing any I/O operations.

        Returns:
            Metadata describing this data source
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the data source is healthy and reachable.

        This should perform a lightweight check to verify the source is working.

        Returns:
            True if healthy, False otherwise
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """
        Clean up resources used by this data source.

        This is called at application shutdown and should:
        - Stop background tasks
        - Close connections
        - Release resources
        """
        pass
