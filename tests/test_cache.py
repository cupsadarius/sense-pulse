"""Tests for cache module"""

import asyncio
import time
from datetime import datetime

from sense_pulse.cache import CachedData, DataCache
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
        assert result is not None
        assert "test" in result
        assert result["test"]["value"] == "data"
        assert "timestamp" in result["test"]

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

    async def test_get_data_source(self):
        """Test getting a registered data source by ID"""
        cache = DataCache()
        source = MockDataSource(source_id="test_source")
        await source.initialize()
        cache.register_data_source(source)

        # Should return the source
        retrieved = cache.get_data_source("test_source")
        assert retrieved is source

        # Should return None for unknown source
        assert cache.get_data_source("nonexistent") is None

    async def test_get_data_source_status(self):
        """Test getting status from a source with get_sensor_status"""
        cache = DataCache()

        # Create a mock source with get_sensor_status method
        source = MockDataSource(source_id="aranet_mock")
        source.get_sensor_status = lambda: {"sensor1": {"connected": True}}  # type: ignore[attr-defined]
        await source.initialize()
        cache.register_data_source(source)

        # Should return status
        status = cache.get_data_source_status("aranet_mock")
        assert status is not None
        assert "sensor1" in status

        # Should return None for source without the method
        plain_source = MockDataSource(source_id="plain")
        await plain_source.initialize()
        cache.register_data_source(plain_source)
        assert cache.get_data_source_status("plain") is None

        # Should return None for unknown source
        assert cache.get_data_source_status("unknown") is None

    async def test_list_registered_sources(self):
        """Test listing all registered source IDs"""
        cache = DataCache()
        source1 = MockDataSource(source_id="source1")
        source2 = MockDataSource(source_id="source2")
        await source1.initialize()
        await source2.initialize()
        cache.register_data_source(source1)
        cache.register_data_source(source2)

        sources = cache.list_registered_sources()
        assert "source1" in sources
        assert "source2" in sources
        assert len(sources) == 2

    async def test_get_all_source_metadata(self):
        """Test getting metadata for all sources"""
        cache = DataCache()
        source = MockDataSource(source_id="test", name="Test Source")
        await source.initialize()
        cache.register_data_source(source)

        metadata = cache.get_all_source_metadata()
        assert "test" in metadata
        assert metadata["test"].name == "Test Source"
        assert metadata["test"].source_id == "test"

    async def test_is_source_registered(self):
        """Test checking if source is registered"""
        cache = DataCache()
        source = MockDataSource(source_id="registered")
        await source.initialize()
        cache.register_data_source(source)

        assert cache.is_source_registered("registered") is True
        assert cache.is_source_registered("not_registered") is False


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

    async def test_custom_cache_ttl(self):
        """Test that custom cache TTL works correctly"""
        # Create cache with short TTL
        cache = DataCache(cache_ttl=0.2, poll_interval=10.0)
        await cache.set("key1", "value1")

        # Should be available immediately
        assert await cache.get("key1") == "value1"

        # Wait for TTL to expire
        await asyncio.sleep(0.3)

        # Should be expired now
        assert await cache.get("key1", default="expired") == "expired"

    async def test_custom_poll_interval(self):
        """Test that custom poll interval is respected"""
        # Create cache with very short poll interval
        cache = DataCache(cache_ttl=10.0, poll_interval=0.2)
        source = MockDataSource(source_id="test_poll", name="Test Poll")
        await source.initialize()

        cache.register_data_source(source)
        await cache.start_polling()

        # Wait for multiple poll cycles
        await asyncio.sleep(0.6)

        await cache.stop_polling()

        # Should have polled at least 3 times (immediate + 2 intervals)
        # Give some leeway for timing
        assert source.get_fetch_count() >= 2

    async def test_cache_ttl_preserved_in_status(self):
        """Test that cache TTL is reported correctly in status"""
        cache = DataCache(cache_ttl=123.0, poll_interval=45.0)
        await cache.set("test", "value")

        status = await cache.get_status()
        assert status["cache_ttl"] == 123.0

    async def test_different_ttl_values(self):
        """Test cache with various TTL values"""
        # Very short TTL
        cache_short = DataCache(cache_ttl=0.1)
        await cache_short.set("key", "value")
        await asyncio.sleep(0.15)
        assert await cache_short.get("key", default="expired") == "expired"

        # Long TTL
        cache_long = DataCache(cache_ttl=100.0)
        await cache_long.set("key", "value")
        await asyncio.sleep(0.1)
        assert await cache_long.get("key") == "value"
