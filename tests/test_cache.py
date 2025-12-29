"""Tests for cache module"""

import time
from unittest.mock import Mock

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

    def test_set_and_get(self):
        """Test basic set/get operations"""
        cache = DataCache()
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        assert cache.get("nonexistent", default="default") == "default"

    def test_get_expired(self):
        """Test getting expired data"""
        cache = DataCache(cache_ttl=0.1)
        cache.set("key1", "value1")
        time.sleep(0.15)
        assert cache.get("key1", default="expired") == "expired"

    def test_get_all(self):
        """Test getting all non-expired data"""
        cache = DataCache(cache_ttl=1.0)
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        all_data = cache.get_all()
        assert "key1" in all_data
        assert "key2" in all_data
        assert all_data["key1"] == "value1"

    def test_register_source(self):
        """Test registering a data source"""
        cache = DataCache()
        mock_func = Mock(return_value={"test": "data"})

        cache.register_source("test_source", mock_func)
        assert "test_source" in cache._data_sources

    def test_poll_data_source(self):
        """Test polling a single data source"""
        cache = DataCache()
        mock_func = Mock(return_value={"test": "data"})

        cache._poll_data_source("test_key", mock_func)

        mock_func.assert_called_once()
        assert cache.get("test_key") == {"test": "data"}

    def test_poll_data_source_error(self):
        """Test polling handles errors gracefully"""
        cache = DataCache()
        mock_func = Mock(side_effect=Exception("Test error"))

        # Should not raise, but log error
        cache._poll_data_source("test_key", mock_func)

        # Data should not be cached
        assert cache.get("test_key") is None

    def test_get_status(self):
        """Test cache status reporting"""
        cache = DataCache(cache_ttl=1.0)
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        status = cache.get_status()

        assert status["total_entries"] == 2
        assert status["valid_entries"] == 2
        assert status["cache_ttl"] == 1.0
        assert "data_ages" in status

    def test_clear(self):
        """Test clearing cache"""
        cache = DataCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None


class TestGlobalCache:
    """Test global cache singleton"""

    def test_get_cache_singleton(self):
        """Test that get_cache returns singleton"""
        cache1 = get_cache()
        cache2 = get_cache()
        assert cache1 is cache2

    def test_initialize_cache(self):
        """Test explicit cache initialization"""
        cache = initialize_cache(cache_ttl=120, poll_interval=60)
        assert cache.cache_ttl == 120
        assert cache.poll_interval == 60

        # Should be the global instance
        assert get_cache() is cache


class TestCachePolling:
    """Test background polling functionality"""

    def test_start_and_stop_polling(self):
        """Test starting and stopping background polling"""
        cache = DataCache(poll_interval=0.5)
        mock_func = Mock(return_value={"test": "data"})

        cache.register_source("test_source", mock_func)
        cache.start_polling()

        # Should do immediate poll
        time.sleep(0.1)
        assert mock_func.called

        cache.stop_polling()

        # Thread should stop
        if cache._polling_thread:
            assert not cache._polling_thread.is_alive()

    def test_polling_updates_cache(self):
        """Test that polling updates cache periodically"""
        cache = DataCache(cache_ttl=10, poll_interval=0.2)
        counter = {"value": 0}

        def mock_func():
            counter["value"] += 1
            return {"count": counter["value"]}

        cache.register_source("counter", mock_func)
        cache.start_polling()

        # Wait for multiple polls
        time.sleep(0.5)

        cache.stop_polling()

        # Should have polled multiple times
        data = cache.get("counter")
        assert data is not None
        assert data["count"] >= 2  # At least immediate poll + 1 interval

    def test_start_polling_when_already_running(self):
        """Test that starting polling twice doesn't create duplicate threads"""
        cache = DataCache(poll_interval=1.0)

        cache.start_polling()
        cache.start_polling()  # Should be no-op

        cache.stop_polling()
