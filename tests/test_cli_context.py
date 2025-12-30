"""Tests for CLI with AppContext integration."""

import pytest

from sense_pulse.config import Config
from sense_pulse.context import AppContext
from tests.mock_datasource import MockDataSource


class TestCLIContextIntegration:
    """Test CLI creates and uses AppContext correctly."""

    @pytest.mark.asyncio
    async def test_context_lifecycle(self):
        """Test context start and shutdown work correctly."""
        config = Config()
        context = AppContext.create(config, poll_interval=1.0)

        source = MockDataSource(source_id="test")
        context.add_data_source(source)

        # Start
        await context.start()
        assert context.is_started
        assert source.is_initialized()
        assert "test" in context.cache.list_registered_sources()

        # Shutdown
        await context.shutdown()
        assert not context.is_started
        assert source.is_shutdown()

    @pytest.mark.asyncio
    async def test_multiple_data_sources(self):
        """Test context handles multiple data sources."""
        config = Config()
        context = AppContext.create(config, poll_interval=1.0)

        sources = [
            MockDataSource(source_id="tailscale"),
            MockDataSource(source_id="pihole"),
            MockDataSource(source_id="system"),
            MockDataSource(source_id="sensors"),
            MockDataSource(source_id="co2"),
        ]

        for source in sources:
            context.add_data_source(source)

        await context.start()

        try:
            assert len(context.cache.list_registered_sources()) == 5
            for source in sources:
                assert source.is_initialized()
        finally:
            await context.shutdown()

    @pytest.mark.asyncio
    async def test_context_passed_to_web_app(self):
        """Test context is correctly passed to create_app."""
        from sense_pulse.web.app import create_app, get_app_context

        config = Config()
        context = AppContext.create(config, poll_interval=1.0)
        await context.start()

        try:
            app = create_app(context=context)

            assert app.state.context is context
            assert get_app_context() is context
        finally:
            await context.shutdown()

    @pytest.mark.asyncio
    async def test_sense_hat_instance_extracted(self):
        """Test SenseHat instance is extracted from data source."""
        config = Config()
        context = AppContext.create(config, poll_interval=1.0)

        # Create mock source with get_sense_hat_instance method
        source = MockDataSource(source_id="sensors")
        mock_sense_hat = object()  # Mock SenseHat
        source.get_sense_hat_instance = lambda: mock_sense_hat

        context.add_data_source(source)
        await context.start()

        try:
            # Simulate CLI logic to extract SenseHat
            sense_hat_instance = None
            for s in context.data_sources:
                if hasattr(s, "get_sense_hat_instance"):
                    instance = s.get_sense_hat_instance()
                    if instance:
                        context.sense_hat = instance
                        sense_hat_instance = instance
                        break

            assert sense_hat_instance is mock_sense_hat
            assert context.sense_hat is mock_sense_hat
        finally:
            await context.shutdown()
