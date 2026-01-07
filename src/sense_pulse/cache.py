"""
Data caching and background polling service for Sense Pulse.

This module provides a centralized caching layer that:
- Caches all sensor and service data with a 60-second TTL
- Polls all data sources in the background every 30 seconds
- Provides async-safe access to cached data
"""

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .datasources.base import DataSource, DataSourceMetadata

from sense_pulse.web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="cache")


@dataclass
class CachedData:
    """Container for cached data with timestamp."""

    data: Any
    timestamp: float = field(default_factory=time.time)

    def is_expired(self, ttl: float) -> bool:
        """Check if cached data has expired."""
        return time.time() - self.timestamp > ttl

    @property
    def age(self) -> float:
        """Get age of cached data in seconds."""
        return time.time() - self.timestamp


@dataclass
class DataSourceStatus:
    """Status information for a data source."""

    source_id: str
    name: str
    success: bool
    error: Optional[str] = None
    last_update: float = field(default_factory=time.time)

    @property
    def age(self) -> float:
        """Get age of status in seconds."""
        return time.time() - self.last_update


class DataCache:
    """
    Centralized data cache with background polling.

    All sensor and service data is cached for 60 seconds and refreshed
    every 30 seconds in the background to ensure fresh data is always
    available without blocking API requests.
    """

    def __init__(self, cache_ttl: float = 60.0, poll_interval: float = 30.0):
        """
        Initialize the data cache.

        Args:
            cache_ttl: Time-to-live for cached data in seconds (default: 60)
            poll_interval: Interval for background polling in seconds (default: 30)
        """
        self.cache_ttl = cache_ttl
        self.poll_interval = poll_interval
        self._cache: dict[str, CachedData] = {}
        self._lock = asyncio.Lock()
        self._polling_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._data_sources: dict[str, DataSource] = {}
        self._source_status: dict[str, DataSourceStatus] = {}

        logger.info("DataCache initialized", cache_ttl=cache_ttl, poll_interval=poll_interval)

    def register_data_source(self, source: "DataSource") -> None:
        """
        Register a data source for background polling.

        Args:
            source: DataSource object to register
        """
        metadata = source.get_metadata()
        self._data_sources[metadata.source_id] = source
        logger.info(
            "Registered data source",
            source_name=metadata.name,
            source_id=metadata.source_id,
        )

    async def get(self, key: str, default: Any = None) -> Any:
        """
        Get cached data by key.

        Args:
            key: Cache key
            default: Default value if key not found or expired

        Returns:
            Cached data or default value
        """
        async with self._lock:
            cached = self._cache.get(key)
            if cached is None:
                logger.debug("Cache miss", key=key)
                return default

            if cached.is_expired(self.cache_ttl):
                logger.debug("Cache expired", key=key, age=round(cached.age, 1))
                return default

            logger.debug("Cache hit", key=key, age=round(cached.age, 1))
            return cached.data

    async def set(self, key: str, data: Any) -> None:
        """
        Set cached data.

        Args:
            key: Cache key
            data: Data to cache
        """
        async with self._lock:
            self._cache[key] = CachedData(data)
            logger.debug("Cache updated", key=key)

    async def get_all(self) -> dict[str, Any]:
        """
        Get all cached data (non-expired only).

        Returns:
            Dictionary of all cached data
        """
        async with self._lock:
            return {
                key: cached.data
                for key, cached in self._cache.items()
                if not cached.is_expired(self.cache_ttl)
            }

    async def get_status(self) -> dict[str, Any]:
        """
        Get cache status information.

        Returns:
            Dictionary with cache statistics
        """
        async with self._lock:
            total = len(self._cache)
            expired = sum(1 for c in self._cache.values() if c.is_expired(self.cache_ttl))
            ages = {k: c.age for k, c in self._cache.items()}

            return {
                "total_entries": total,
                "valid_entries": total - expired,
                "expired_entries": expired,
                "cache_ttl": self.cache_ttl,
                "poll_interval": self.poll_interval,
                "polling_active": self._polling_task is not None and not self._polling_task.done(),
                "data_ages": ages,
            }

    async def _poll_data_source(self, source: "DataSource") -> None:
        """
        Poll a data source and update cache.

        Args:
            source: DataSource object to poll
        """
        metadata = source.get_metadata()
        key = metadata.source_id

        try:
            logger.debug("Polling data source", source_name=metadata.name, source_id=key)
            readings = await source.fetch_readings()

            # Convert readings to dict format with values and timestamps
            data = {}
            for reading in readings:
                data[reading.sensor_id] = {
                    "value": reading.value,
                    "timestamp": reading.timestamp.timestamp(),
                }

            await self.set(key, data)
            self._source_status[key] = DataSourceStatus(
                source_id=key,
                name=metadata.name,
                success=True,
                error=None,
            )
            logger.debug(
                "Poll completed",
                source_name=metadata.name,
                source_id=key,
                readings_count=len(readings),
            )
        except Exception as e:
            self._source_status[key] = DataSourceStatus(
                source_id=key,
                name=metadata.name,
                success=False,
                error=str(e),
            )
            logger.error(
                "Poll failed",
                source_name=metadata.name,
                source_id=key,
                error=str(e),
                exc_info=True,
            )

    async def _polling_loop(self) -> None:
        """Background polling loop that fetches fresh data periodically."""
        logger.info("Background polling loop started")

        while not self._stop_event.is_set():
            cycle_start = time.time()

            # Poll all data sources
            data_sources = list(self._data_sources.values())
            for source in data_sources:
                if self._stop_event.is_set():
                    break
                await self._poll_data_source(source)

            # Wait for next poll interval
            elapsed = time.time() - cycle_start
            wait_time = max(0, self.poll_interval - elapsed)

            if wait_time > 0:
                logger.debug(
                    "Polling cycle completed",
                    elapsed=round(elapsed, 2),
                    wait_time=round(wait_time, 2),
                )
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._stop_event.wait(), timeout=wait_time)

        logger.info("Background polling loop stopped")

    async def start_polling(self) -> None:
        """Start the background polling task."""
        if self._polling_task is not None and not self._polling_task.done():
            logger.warning("Polling task already running")
            return

        self._stop_event.clear()
        self._polling_task = asyncio.create_task(self._polling_loop())
        logger.info("Background polling task started")

        # Do an immediate poll to populate cache
        data_sources = list(self._data_sources.values())
        for source in data_sources:
            await self._poll_data_source(source)

    async def stop_polling(self) -> None:
        """Stop the background polling task."""
        if self._polling_task is None or self._polling_task.done():
            logger.warning("Polling task not running")
            return

        logger.info("Stopping background polling task...")
        self._stop_event.set()

        try:
            await asyncio.wait_for(self._polling_task, timeout=5.0)
            logger.info("Background polling task stopped")
        except asyncio.TimeoutError:
            logger.warning("Polling task did not stop gracefully, cancelling")
            self._polling_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._polling_task

    async def clear(self) -> None:
        """Clear all cached data."""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info("Cache cleared", entries_cleared=count)

    # =========================================================================
    # PUBLIC API FOR DATA SOURCE ACCESS
    # =========================================================================

    def get_data_source(self, source_id: str) -> Optional["DataSource"]:
        """
        Get a registered data source by ID.

        This provides public access to data sources without exposing
        the internal _data_sources dict.

        Args:
            source_id: The source identifier (e.g., "co2", "tailscale")

        Returns:
            The DataSource instance, or None if not found
        """
        return self._data_sources.get(source_id)

    def get_data_source_status(self, source_id: str) -> Optional[dict[str, Any]]:
        """
        Get status from a data source that supports the get_sensor_status method.

        This is specifically for Aranet4-style sources that provide detailed
        sensor status beyond just readings.

        Args:
            source_id: The source identifier

        Returns:
            Status dict from the source, or None if not available
        """
        source = self._data_sources.get(source_id)
        if source and hasattr(source, "get_sensor_status"):
            return source.get_sensor_status()  # type: ignore[no-any-return]
        return None

    def list_registered_sources(self) -> list[str]:
        """
        Get list of all registered data source IDs.

        Returns:
            List of source IDs (e.g., ["tailscale", "pihole", "system"])
        """
        return list(self._data_sources.keys())

    def get_all_source_metadata(self) -> dict[str, "DataSourceMetadata"]:
        """
        Get metadata for all registered data sources.

        Returns:
            Dict mapping source_id to DataSourceMetadata
        """
        return {
            source_id: source.get_metadata() for source_id, source in self._data_sources.items()
        }

    def is_source_registered(self, source_id: str) -> bool:
        """
        Check if a data source is registered.

        Args:
            source_id: The source identifier to check

        Returns:
            True if source is registered, False otherwise
        """
        return source_id in self._data_sources

    def get_all_source_status(self) -> list[dict[str, Any]]:
        """
        Get status information for all registered data sources.

        Returns:
            List of status dicts with source_id, name, success, error, and last_update
        """
        return [
            {
                "source_id": status.source_id,
                "name": status.name,
                "success": status.success,
                "error": status.error,
                "last_update": status.last_update,
                "age": status.age,
            }
            for status in self._source_status.values()
        ]
