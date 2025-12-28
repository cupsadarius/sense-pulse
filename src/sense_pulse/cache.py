"""
Data caching and background polling service for Sense Pulse.

This module provides a centralized caching layer that:
- Caches all sensor and service data with a 60-second TTL
- Polls all data sources in the background every 30 seconds
- Provides thread-safe access to cached data
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

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
        self._lock = threading.RLock()
        self._polling_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._data_sources: dict[str, callable] = {}

        logger.info(
            f"DataCache initialized with {cache_ttl}s TTL and {poll_interval}s poll interval"
        )

    def register_source(self, key: str, fetch_func: callable) -> None:
        """
        Register a data source for background polling.

        Args:
            key: Cache key for this data source
            fetch_func: Callable that fetches fresh data (no arguments)
        """
        with self._lock:
            self._data_sources[key] = fetch_func
            logger.info(f"Registered data source: {key}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get cached data by key.

        Args:
            key: Cache key
            default: Default value if key not found or expired

        Returns:
            Cached data or default value
        """
        with self._lock:
            cached = self._cache.get(key)
            if cached is None:
                logger.debug(f"Cache miss: {key}")
                return default

            if cached.is_expired(self.cache_ttl):
                logger.debug(f"Cache expired: {key} (age: {cached.age:.1f}s)")
                return default

            logger.debug(f"Cache hit: {key} (age: {cached.age:.1f}s)")
            return cached.data

    def set(self, key: str, data: Any) -> None:
        """
        Set cached data.

        Args:
            key: Cache key
            data: Data to cache
        """
        with self._lock:
            self._cache[key] = CachedData(data)
            logger.debug(f"Cache updated: {key}")

    def get_all(self) -> dict[str, Any]:
        """
        Get all cached data (non-expired only).

        Returns:
            Dictionary of all cached data
        """
        with self._lock:
            return {
                key: cached.data
                for key, cached in self._cache.items()
                if not cached.is_expired(self.cache_ttl)
            }

    def get_status(self) -> dict[str, Any]:
        """
        Get cache status information.

        Returns:
            Dictionary with cache statistics
        """
        with self._lock:
            total = len(self._cache)
            expired = sum(
                1 for c in self._cache.values() if c.is_expired(self.cache_ttl)
            )
            ages = {k: c.age for k, c in self._cache.items()}

            return {
                "total_entries": total,
                "valid_entries": total - expired,
                "expired_entries": expired,
                "cache_ttl": self.cache_ttl,
                "poll_interval": self.poll_interval,
                "polling_active": self._polling_thread is not None
                and self._polling_thread.is_alive(),
                "data_ages": ages,
            }

    def _poll_data_source(self, key: str, fetch_func: callable) -> None:
        """
        Poll a single data source and update cache.

        Args:
            key: Cache key
            fetch_func: Function to fetch data
        """
        try:
            logger.debug(f"Polling data source: {key}")
            data = fetch_func()
            self.set(key, data)
            logger.debug(f"Successfully polled: {key}")
        except Exception as e:
            logger.error(f"Error polling {key}: {e}", exc_info=True)

    def _polling_loop(self) -> None:
        """Background polling loop that fetches fresh data periodically."""
        logger.info("Background polling loop started")

        while not self._stop_event.is_set():
            cycle_start = time.time()

            # Poll all registered data sources
            with self._lock:
                sources = list(self._data_sources.items())

            for key, fetch_func in sources:
                if self._stop_event.is_set():
                    break
                self._poll_data_source(key, fetch_func)

            # Wait for next poll interval
            elapsed = time.time() - cycle_start
            wait_time = max(0, self.poll_interval - elapsed)

            if wait_time > 0:
                logger.debug(
                    f"Polling cycle completed in {elapsed:.2f}s, waiting {wait_time:.2f}s"
                )
                self._stop_event.wait(wait_time)

        logger.info("Background polling loop stopped")

    def start_polling(self) -> None:
        """Start the background polling thread."""
        if self._polling_thread is not None and self._polling_thread.is_alive():
            logger.warning("Polling thread already running")
            return

        self._stop_event.clear()
        self._polling_thread = threading.Thread(
            target=self._polling_loop, name="DataCachePoller", daemon=True
        )
        self._polling_thread.start()
        logger.info("Background polling thread started")

        # Do an immediate poll to populate cache
        with self._lock:
            sources = list(self._data_sources.items())
        for key, fetch_func in sources:
            self._poll_data_source(key, fetch_func)

    def stop_polling(self) -> None:
        """Stop the background polling thread."""
        if self._polling_thread is None or not self._polling_thread.is_alive():
            logger.warning("Polling thread not running")
            return

        logger.info("Stopping background polling thread...")
        self._stop_event.set()
        self._polling_thread.join(timeout=5.0)

        if self._polling_thread.is_alive():
            logger.warning("Polling thread did not stop gracefully")
        else:
            logger.info("Background polling thread stopped")

    def clear(self) -> None:
        """Clear all cached data."""
        with self._lock:
            self._cache.clear()
            logger.info("Cache cleared")


# Global cache instance
_global_cache: Optional[DataCache] = None
_cache_lock = threading.Lock()


def get_cache() -> DataCache:
    """
    Get the global cache instance.

    Returns:
        Global DataCache instance
    """
    global _global_cache
    if _global_cache is None:
        with _cache_lock:
            if _global_cache is None:
                _global_cache = DataCache()
    return _global_cache


def initialize_cache(cache_ttl: float = 60.0, poll_interval: float = 30.0) -> DataCache:
    """
    Initialize the global cache instance.

    Args:
        cache_ttl: Time-to-live for cached data in seconds
        poll_interval: Interval for background polling in seconds

    Returns:
        Initialized DataCache instance
    """
    global _global_cache
    with _cache_lock:
        if _global_cache is not None:
            logger.warning("Cache already initialized, stopping existing cache")
            _global_cache.stop_polling()

        _global_cache = DataCache(cache_ttl, poll_interval)
        logger.info(f"Global cache initialized (TTL: {cache_ttl}s, Poll: {poll_interval}s)")
        return _global_cache
