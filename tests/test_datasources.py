"""Tests for data source architecture"""

import asyncio
from datetime import datetime

import pytest

from sense_pulse.cache import DataCache
from sense_pulse.datasources.base import DataSourceMetadata, SensorReading
from sense_pulse.datasources.registry import DataSourceRegistry
from tests.mock_datasource import MockDataSource


class TestMockDataSource:
    """Test the mock data source implementation"""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test data source initialization"""
        source = MockDataSource(source_id="test", name="Test Source")
        assert not source.is_initialized()

        await source.initialize()
        assert source.is_initialized()

    @pytest.mark.asyncio
    async def test_fetch_readings(self):
        """Test fetching readings"""
        readings = [
            SensorReading("temp", 25.5, "°C", datetime.now()),
            SensorReading("humidity", 60, "%", datetime.now()),
        ]
        source = MockDataSource(source_id="test", readings=readings)
        await source.initialize()

        result = await source.fetch_readings()
        assert len(result) == 2
        assert result[0].sensor_id == "temp"
        assert result[0].value == 25.5
        assert result[1].sensor_id == "humidity"
        assert result[1].value == 60

    @pytest.mark.asyncio
    async def test_metadata(self):
        """Test metadata retrieval"""
        source = MockDataSource(source_id="test", name="Test Source")
        metadata = source.get_metadata()

        assert isinstance(metadata, DataSourceMetadata)
        assert metadata.source_id == "test"
        assert metadata.name == "Test Source"
        assert metadata.enabled is True

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check"""
        source = MockDataSource(source_id="test")

        # Before initialization, health check should fail
        assert not await source.health_check()

        # After initialization, should pass
        await source.initialize()
        assert await source.health_check()

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test shutdown"""
        source = MockDataSource(source_id="test")
        await source.initialize()
        assert not source.is_shutdown()

        await source.shutdown()
        assert source.is_shutdown()

    @pytest.mark.asyncio
    async def test_failure_modes(self):
        """Test various failure modes"""
        # Test initialization failure
        source = MockDataSource(source_id="test", fail_on_initialize=True)
        with pytest.raises(RuntimeError, match="Mock initialization failure"):
            await source.initialize()

        # Test fetch failure
        source = MockDataSource(source_id="test", fail_on_fetch=True)
        await source.initialize()
        with pytest.raises(RuntimeError, match="Mock fetch failure"):
            await source.fetch_readings()

        # Test health check failure
        source = MockDataSource(source_id="test", fail_on_health_check=True)
        await source.initialize()
        assert not await source.health_check()


class TestDataSourceRegistry:
    """Test the data source registry"""

    @pytest.mark.asyncio
    async def test_register_source(self):
        """Test registering data sources"""
        registry = DataSourceRegistry()
        source = MockDataSource(source_id="test1", name="Test Source 1")

        registry.register(source)
        assert len(registry) == 1
        assert "test1" in registry

    @pytest.mark.asyncio
    async def test_duplicate_registration(self):
        """Test that duplicate registration raises error"""
        registry = DataSourceRegistry()
        source1 = MockDataSource(source_id="test1")
        source2 = MockDataSource(source_id="test1")

        registry.register(source1)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(source2)

    @pytest.mark.asyncio
    async def test_get_source(self):
        """Test retrieving sources"""
        registry = DataSourceRegistry()
        source = MockDataSource(source_id="test1", name="Test Source")

        registry.register(source)
        retrieved = registry.get("test1")
        assert retrieved is source

    @pytest.mark.asyncio
    async def test_get_all_sources(self):
        """Test getting all sources"""
        registry = DataSourceRegistry()
        source1 = MockDataSource(source_id="test1")
        source2 = MockDataSource(source_id="test2")

        registry.register(source1)
        registry.register(source2)

        all_sources = registry.get_all()
        assert len(all_sources) == 2
        assert source1 in all_sources
        assert source2 in all_sources

    @pytest.mark.asyncio
    async def test_get_enabled_sources(self):
        """Test getting only enabled sources"""
        registry = DataSourceRegistry()
        source1 = MockDataSource(source_id="test1", enabled=True)
        source2 = MockDataSource(source_id="test2", enabled=False)

        registry.register(source1)
        registry.register(source2)

        enabled = registry.get_enabled()
        assert len(enabled) == 1
        assert source1 in enabled
        assert source2 not in enabled

    @pytest.mark.asyncio
    async def test_initialize_all(self):
        """Test initializing all sources"""
        registry = DataSourceRegistry()
        source1 = MockDataSource(source_id="test1")
        source2 = MockDataSource(source_id="test2")

        registry.register(source1)
        registry.register(source2)

        await registry.initialize_all()
        assert source1.is_initialized()
        assert source2.is_initialized()

    @pytest.mark.asyncio
    async def test_shutdown_all(self):
        """Test shutting down all sources"""
        registry = DataSourceRegistry()
        source1 = MockDataSource(source_id="test1")
        source2 = MockDataSource(source_id="test2")

        registry.register(source1)
        registry.register(source2)
        await registry.initialize_all()

        await registry.shutdown_all()
        assert source1.is_shutdown()
        assert source2.is_shutdown()


class TestCacheIntegration:
    """Test cache integration with data sources"""

    @pytest.mark.asyncio
    async def test_register_data_source_with_cache(self):
        """Test registering a data source with cache"""
        cache = DataCache(cache_ttl=60.0, poll_interval=30.0)
        source = MockDataSource(source_id="test", name="Test Source")

        await source.initialize()
        cache.register_data_source(source)

        # Manually poll once
        await cache._poll_data_source(source)

        # Check that data is in cache
        data = await cache.get("test")
        assert data is not None
        assert "test_test" in data  # sensor_id from default reading
        assert data["test_test"]["value"] == 42
        assert "timestamp" in data["test_test"]

    @pytest.mark.asyncio
    async def test_cache_polling_with_data_source(self):
        """Test that cache polls data source in background"""
        cache = DataCache(cache_ttl=60.0, poll_interval=0.5)  # Short interval for testing
        readings = [
            SensorReading("temp", 25.5, "°C", datetime.now()),
            SensorReading("humidity", 60, "%", datetime.now()),
        ]
        source = MockDataSource(source_id="test", readings=readings)

        await source.initialize()
        cache.register_data_source(source)

        # Start polling
        await cache.start_polling()

        # Wait for at least one poll cycle
        await asyncio.sleep(0.6)

        # Check that data was fetched
        assert source.get_fetch_count() >= 1

        # Check cache contents
        data = await cache.get("test")
        assert data is not None
        assert "temp" in data
        assert data["temp"]["value"] == 25.5
        assert "timestamp" in data["temp"]
        assert "humidity" in data
        assert data["humidity"]["value"] == 60
        assert "timestamp" in data["humidity"]

        # Stop polling
        await cache.stop_polling()

    @pytest.mark.asyncio
    async def test_multiple_sources_with_cache(self):
        """Test multiple data sources with cache"""
        cache = DataCache(cache_ttl=60.0, poll_interval=30.0)

        source1 = MockDataSource(
            source_id="source1",
            readings=[SensorReading("sensor1", 100, "units", datetime.now())],
        )
        source2 = MockDataSource(
            source_id="source2",
            readings=[SensorReading("sensor2", 200, "units", datetime.now())],
        )

        await source1.initialize()
        await source2.initialize()

        cache.register_data_source(source1)
        cache.register_data_source(source2)

        # Manually trigger polling
        await cache._poll_data_source(source1)
        await cache._poll_data_source(source2)

        # Check both sources are cached
        data1 = await cache.get("source1")
        data2 = await cache.get("source2")

        assert data1 is not None
        assert "sensor1" in data1
        assert data1["sensor1"]["value"] == 100
        assert "timestamp" in data1["sensor1"]

        assert data2 is not None
        assert "sensor2" in data2
        assert data2["sensor2"]["value"] == 200
        assert "timestamp" in data2["sensor2"]

    @pytest.mark.asyncio
    async def test_cache_handles_source_errors(self):
        """Test that cache handles data source errors gracefully"""
        cache = DataCache(cache_ttl=60.0, poll_interval=30.0)
        source = MockDataSource(source_id="test", fail_on_fetch=True)

        await source.initialize()
        cache.register_data_source(source)

        # This should not raise an exception
        await cache._poll_data_source(source)

        # Cache should return default value
        data = await cache.get("test", default={})
        assert data == {}
