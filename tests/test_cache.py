"""Tests for cache module"""

import asyncio
import time
from datetime import datetime

from sense_pulse.cache import CachedData, DataCache, get_cache, initialize_cache
from sense_pulse.datasources.base import SensorReading
from tests.mock_datasource import MockDataSource


class TestCachedData:
    """Test CachedData class"""

    def test_is_expired(self):
        """Test expiration checking"""
        data = CachedData(data="test", timestamp=time.time() - 10)
        assert data.is_expired(ttl=5) is True
        assert data.is_expired(ttl=15) is False

    def test_age(self):
        """Test age calculation"""
        start = time.time()
        data = CachedData(data="test", timestamp=start)
        time.sleep(0.1)
        assert data.age >= 0.1
        assert data.age < 0.2


class TestDataCache:
    """Test DataCache class"""

    def test_initialization(self):
        """Test cache initialization"""
        cache = DataCache(cache_ttl=60, poll_interval=30)
        assert cache.cache_ttl == 60
        assert cache.poll_interval == 30

    async def test_set_and_get(self):
        """Test basic set/get operations"""
        cache = DataCache()
        await cache.set("key1", "value1")
        assert await cache.get("key1") == "value1"
        assert await cache.get("nonexistent", default="default") == "default"

    async def test_get_expired(self):
        """Test getting expired data"""
        cache = DataCache(cache_ttl=0.1)
        await cache.set("key1", "value1")
        time.sleep(0.15)
        assert await cache.get("key1", default="expired") == "expired"

    async def test_get_all(self):
        """Test getting all non-expired data"""
        cache = DataCache(cache_ttl=1.0)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        all_data = await cache.get_all()
        assert "key1" in all_data
        assert "key2" in all_data
        assert all_data["key1"] == "value1"

    async def test_register_source(self):
        """Test registering a data source"""
        cache = DataCache()
        source = MockDataSource(source_id="test_source", name="Test Source")
        await source.initialize()

        cache.register_data_source(source)
        assert "test_source" in cache._data_sources

    async def test_poll_data_source(self):
        """Test polling a single data source"""
        cache = DataCache()
        readings = [SensorReading("test", "data", None, datetime.now())]
        source = MockDataSource(source_id="test_key", readings=readings)
        await source.initialize()

        await cache._poll_data_source(source)
        result = await cache.get("test_key")
        assert result == {"test": "data"}

    async def test_poll_data_source_error(self):
        """Test polling handles errors gracefully"""
        cache = DataCache()
        source = MockDataSource(source_id="test_key", fail_on_fetch=True)
        await source.initialize()

        # Should not raise, but log error
        await cache._poll_data_source(source)

        # Data should not be cached
        assert await cache.get("test_key") is None

    async def test_get_status(self):
        """Test cache status reporting"""
        cache = DataCache(cache_ttl=1.0)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        status = await cache.get_status()

        assert status["total_entries"] == 2
        assert status["valid_entries"] == 2
        assert status["cache_ttl"] == 1.0
        assert "data_ages" in status

    async def test_clear(self):
        """Test clearing cache"""
        cache = DataCache()
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        await cache.clear()

        assert await cache.get("key1") is None
        assert await cache.get("key2") is None


class TestGlobalCache:
    """Test global cache singleton"""

    async def test_get_cache_singleton(self):
        """Test that get_cache returns singleton"""
        cache1 = await get_cache()
        cache2 = await get_cache()
        assert cache1 is cache2

    async def test_initialize_cache(self):
        """Test explicit cache initialization"""
        cache = await initialize_cache(cache_ttl=120, poll_interval=60)
        assert cache.cache_ttl == 120
        assert cache.poll_interval == 60

        # Should be the global instance
        assert await get_cache() is cache


class TestCachePolling:
    """Test background polling functionality"""

    async def test_start_and_stop_polling(self):
        """Test starting and stopping background polling"""
        cache = DataCache(poll_interval=0.5)
        source = MockDataSource(source_id="test_source", name="Test Source")
        await source.initialize()

        cache.register_data_source(source)
        await cache.start_polling()

        # Should do immediate poll
        await asyncio.sleep(0.1)
        assert source.get_fetch_count() > 0

        await cache.stop_polling()

        # Task should be done
        if cache._polling_task:
            assert cache._polling_task.done()

    async def test_polling_updates_cache(self):
        """Test that polling updates cache periodically"""
        cache = DataCache(cache_ttl=10, poll_interval=0.2)
        source = MockDataSource(source_id="counter", name="Counter Source")
        await source.initialize()

        cache.register_data_source(source)
        await cache.start_polling()

        # Wait for multiple polls
        await asyncio.sleep(0.5)

        await cache.stop_polling()

        # Should have polled multiple times
        data = await cache.get("counter")
        assert data is not None
        assert source.get_fetch_count() >= 2  # At least immediate poll + 1 interval

    async def test_start_polling_when_already_running(self):
        """Test that starting polling twice doesn't create duplicate tasks"""
        cache = DataCache(poll_interval=1.0)
        source = MockDataSource(source_id="test", name="Test Source")
        await source.initialize()

        cache.register_data_source(source)
        await cache.start_polling()
        await cache.start_polling()  # Should be no-op

        await cache.stop_polling()
