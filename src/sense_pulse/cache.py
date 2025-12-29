"""
Data caching and background polling service for Sense Pulse.

This module provides a centralized caching layer that:
- Caches all sensor and service data with a 60-second TTL
- Polls all data sources in the background every 30 seconds
- Provides async-safe access to cached data
"""

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .datasources.base import DataSource

logger = logging.getLogger(__name__)


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
        self._data_sources: dict[str, "DataSource"] = {}
        # Legacy support: keep old-style callables for backward compatibility
        self._legacy_sources: dict[str, Callable] = {}

        logger.info(
            f"DataCache initialized with {cache_ttl}s TTL and {poll_interval}s poll interval"
        )

    def register_source(self, key: str, fetch_func: Callable) -> None:
        """
        Register a legacy data source (for backward compatibility).

        Args:
            key: Cache key for this data source
            fetch_func: Async callable that fetches fresh data (no arguments)

        DEPRECATED: Use register_data_source() with a DataSource object instead.
        """
        self._legacy_sources[key] = fetch_func
        logger.info(f"Registered legacy data source: {key}")

    def register_data_source(self, source: "DataSource") -> None:
        """
        Register a data source for background polling.

        Args:
            source: DataSource object to register
        """
        metadata = source.get_metadata()
        self._data_sources[metadata.source_id] = source
        logger.info(f"Registered data source: {metadata.name} (id={metadata.source_id})")

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
                logger.debug(f"Cache miss: {key}")
                return default

            if cached.is_expired(self.cache_ttl):
                logger.debug(f"Cache expired: {key} (age: {cached.age:.1f}s)")
                return default

            logger.debug(f"Cache hit: {key} (age: {cached.age:.1f}s)")
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
            logger.debug(f"Cache updated: {key}")

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

    async def _poll_data_source(self, key: str, fetch_func: Callable) -> None:
        """
        Poll a single legacy data source and update cache.

        Args:
            key: Cache key
            fetch_func: Async function to fetch data
        """
        try:
            logger.debug(f"Polling legacy data source: {key}")
            data = await fetch_func()
            await self.set(key, data)
            logger.debug(f"Successfully polled: {key}")
        except Exception as e:
            logger.error(f"Error polling {key}: {e}", exc_info=True)

    async def _poll_datasource_object(self, source: "DataSource") -> None:
        """
        Poll a DataSource object and update cache.

        Args:
            source: DataSource object to poll
        """
        metadata = source.get_metadata()
        key = metadata.source_id

        try:
            logger.debug(f"Polling data source: {metadata.name}")
            readings = await source.fetch_readings()

            # Convert readings to dict format for backward compatibility
            data = {}
            for reading in readings:
                data[reading.sensor_id] = reading.value

            await self.set(key, data)
            logger.debug(f"Successfully polled: {metadata.name} ({len(readings)} readings)")
        except Exception as e:
            logger.error(f"Error polling {metadata.name}: {e}", exc_info=True)

    async def _polling_loop(self) -> None:
        """Background polling loop that fetches fresh data periodically."""
        logger.info("Background polling loop started")

        while not self._stop_event.is_set():
            cycle_start = time.time()

            # Poll all DataSource objects
            data_sources = list(self._data_sources.values())
            for source in data_sources:
                if self._stop_event.is_set():
                    break
                await self._poll_datasource_object(source)

            # Poll all legacy sources (for backward compatibility)
            legacy_sources = list(self._legacy_sources.items())
            for key, fetch_func in legacy_sources:
                if self._stop_event.is_set():
                    break
                await self._poll_data_source(key, fetch_func)

            # Wait for next poll interval
            elapsed = time.time() - cycle_start
            wait_time = max(0, self.poll_interval - elapsed)

            if wait_time > 0:
                logger.debug(f"Polling cycle completed in {elapsed:.2f}s, waiting {wait_time:.2f}s")
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
        # Poll DataSource objects
        data_sources = list(self._data_sources.values())
        for source in data_sources:
            await self._poll_datasource_object(source)

        # Poll legacy sources
        legacy_sources = list(self._legacy_sources.items())
        for key, fetch_func in legacy_sources:
            await self._poll_data_source(key, fetch_func)

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
            self._cache.clear()
            logger.info("Cache cleared")


# Global cache instance
_global_cache: Optional[DataCache] = None
_cache_lock = asyncio.Lock()


async def get_cache() -> DataCache:
    """
    Get the global cache instance.

    Returns:
        Global DataCache instance
    """
    global _global_cache
    if _global_cache is None:
        async with _cache_lock:
            if _global_cache is None:
                _global_cache = DataCache()
    return _global_cache


async def initialize_cache(cache_ttl: float = 60.0, poll_interval: float = 30.0) -> DataCache:
    """
    Initialize the global cache instance.

    Args:
        cache_ttl: Time-to-live for cached data in seconds
        poll_interval: Interval for background polling in seconds

    Returns:
        Initialized DataCache instance
    """
    global _global_cache
    async with _cache_lock:
        if _global_cache is not None:
            logger.warning("Cache already initialized, stopping existing cache")
            await _global_cache.stop_polling()

        _global_cache = DataCache(cache_ttl, poll_interval)
        logger.info(f"Global cache initialized (TTL: {cache_ttl}s, Poll: {poll_interval}s)")
        return _global_cache
