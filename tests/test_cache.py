"""Tests for cache module"""

import asyncio
import time

from sense_pulse.cache import CachedData, DataCache, get_cache, initialize_cache


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

    def test_register_source(self):
        """Test registering a data source"""
        cache = DataCache()

        def mock_func():
            return {"test": "data"}

        cache.register_source("test_source", mock_func)
        assert "test_source" in cache._data_sources

    async def test_poll_data_source(self):
        """Test polling a single data source"""
        cache = DataCache()

        async def mock_func():
            return {"test": "data"}

        await cache._poll_data_source("test_key", mock_func)
        assert await cache.get("test_key") == {"test": "data"}

    async def test_poll_data_source_error(self):
        """Test polling handles errors gracefully"""
        cache = DataCache()

        async def mock_func():
            raise Exception("Test error")

        # Should not raise, but log error
        await cache._poll_data_source("test_key", mock_func)

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
        call_count = {"value": 0}

        async def mock_func():
            call_count["value"] += 1
            return {"test": "data"}

        cache.register_source("test_source", mock_func)
        await cache.start_polling()

        # Should do immediate poll
        await asyncio.sleep(0.1)
        assert call_count["value"] > 0

        await cache.stop_polling()

        # Task should be done
        if cache._polling_task:
            assert cache._polling_task.done()

    async def test_polling_updates_cache(self):
        """Test that polling updates cache periodically"""
        cache = DataCache(cache_ttl=10, poll_interval=0.2)
        counter = {"value": 0}

        async def mock_func():
            counter["value"] += 1
            return {"count": counter["value"]}

        cache.register_source("counter", mock_func)
        await cache.start_polling()

        # Wait for multiple polls
        await asyncio.sleep(0.5)

        await cache.stop_polling()

        # Should have polled multiple times
        data = await cache.get("counter")
        assert data is not None
        assert data["count"] >= 2  # At least immediate poll + 1 interval

    async def test_start_polling_when_already_running(self):
        """Test that starting polling twice doesn't create duplicate tasks"""
        cache = DataCache(poll_interval=1.0)

        async def mock_func():
            return {}

        cache.register_source("test", mock_func)
        await cache.start_polling()
        await cache.start_polling()  # Should be no-op

        await cache.stop_polling()
