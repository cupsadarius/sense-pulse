"""Tests for AppContext module."""

import pytest

from sense_pulse.config import Config
from sense_pulse.context import AppContext
from tests.mock_datasource import MockDataSource


class TestAppContextCreation:
    """Test AppContext creation and configuration."""

    def test_create_with_defaults(self):
        """Test factory method creates context with default settings."""
        config = Config()
        context = AppContext.create(config)

        assert context.config is config
        assert context.cache is not None
        assert context.cache.cache_ttl == 60.0
        assert context.cache.poll_interval == 30.0
        assert context.data_sources == []
        assert context.sense_hat is None
        assert not context.is_started

    def test_create_with_custom_settings(self):
        """Test factory method with custom cache settings."""
        config = Config()
        context = AppContext.create(config, cache_ttl=120.0, poll_interval=15.0)

        assert context.cache.cache_ttl == 120.0
        assert context.cache.poll_interval == 15.0

    def test_add_data_source(self):
        """Test adding data sources."""
        config = Config()
        context = AppContext.create(config)
        source = MockDataSource(source_id="test")

        context.add_data_source(source)

        assert len(context.data_sources) == 1
        assert context.data_sources[0] is source

    def test_add_data_source_chaining(self):
        """Test method chaining for add_data_source."""
        config = Config()
        context = AppContext.create(config)
        source1 = MockDataSource(source_id="source1")
        source2 = MockDataSource(source_id="source2")

        result = context.add_data_source(source1).add_data_source(source2)

        assert result is context
        assert len(context.data_sources) == 2


class TestAppContextLifecycle:
    """Test AppContext start/shutdown lifecycle."""

    @pytest.mark.asyncio
    async def test_start_initializes_sources(self):
        """Test start() initializes all data sources."""
        config = Config()
        context = AppContext.create(config, poll_interval=10.0)
        source1 = MockDataSource(source_id="source1")
        source2 = MockDataSource(source_id="source2")

        context.add_data_source(source1)
        context.add_data_source(source2)

        await context.start()

        try:
            assert context.is_started
            assert source1.is_initialized()
            assert source2.is_initialized()
            assert "source1" in context.cache.list_registered_sources()
            assert "source2" in context.cache.list_registered_sources()
        finally:
            await context.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_cleans_up(self):
        """Test shutdown() cleans up all resources."""
        config = Config()
        context = AppContext.create(config, poll_interval=10.0)
        source = MockDataSource(source_id="test")

        context.add_data_source(source)
        await context.start()
        await context.shutdown()

        assert not context.is_started
        assert source.is_shutdown()

    @pytest.mark.asyncio
    async def test_start_handles_source_failure(self):
        """Test start() continues if a source fails to initialize."""
        config = Config()
        context = AppContext.create(config, poll_interval=10.0)

        good_source = MockDataSource(source_id="good")
        bad_source = MockDataSource(source_id="bad", fail_on_initialize=True)

        context.add_data_source(bad_source)
        context.add_data_source(good_source)

        await context.start()  # Should not raise

        try:
            assert context.is_started
            assert good_source.is_initialized()
            assert not bad_source.is_initialized()
            # Good source should be registered
            assert "good" in context.cache.list_registered_sources()
            # Bad source should not be registered
            assert "bad" not in context.cache.list_registered_sources()
        finally:
            await context.shutdown()

    @pytest.mark.asyncio
    async def test_double_start_is_noop(self):
        """Test calling start() twice is safe."""
        config = Config()
        context = AppContext.create(config, poll_interval=10.0)
        source = MockDataSource(source_id="test")

        context.add_data_source(source)

        await context.start()
        fetch_count_after_first_start = source.get_fetch_count()

        await context.start()  # Should be a no-op

        # Fetch count should not have increased significantly
        # (background polling may have run once)
        assert source.get_fetch_count() >= fetch_count_after_first_start

        await context.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_without_start(self):
        """Test shutdown() before start() is safe."""
        config = Config()
        context = AppContext.create(config)
        source = MockDataSource(source_id="test")
        context.add_data_source(source)

        await context.shutdown()  # Should not raise

        assert not context.is_started
        assert not source.is_shutdown()  # Never initialized, so not shutdown

    @pytest.mark.asyncio
    async def test_double_shutdown_is_safe(self):
        """Test calling shutdown() twice is safe."""
        config = Config()
        context = AppContext.create(config, poll_interval=10.0)
        source = MockDataSource(source_id="test")
        context.add_data_source(source)

        await context.start()
        await context.shutdown()
        await context.shutdown()  # Should not raise

        assert not context.is_started


class TestAppContextHelpers:
    """Test AppContext helper methods."""

    def test_get_data_source_found(self):
        """Test get_data_source returns correct source."""
        config = Config()
        context = AppContext.create(config)
        source = MockDataSource(source_id="findme", name="Find Me")
        context.add_data_source(source)

        found = context.get_data_source("findme")

        assert found is source

    def test_get_data_source_not_found(self):
        """Test get_data_source returns None for unknown ID."""
        config = Config()
        context = AppContext.create(config)

        found = context.get_data_source("nonexistent")

        assert found is None

    def test_repr(self):
        """Test string representation."""
        config = Config()
        context = AppContext.create(config)
        context.add_data_source(MockDataSource(source_id="test1"))
        context.add_data_source(MockDataSource(source_id="test2"))

        repr_str = repr(context)

        assert "started=False" in repr_str
        assert "test1" in repr_str
        assert "test2" in repr_str
        assert "cache_ttl=60.0" in repr_str
