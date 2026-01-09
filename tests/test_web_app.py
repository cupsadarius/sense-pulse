"""Tests for web application with dependency injection."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from sense_pulse.config import Config
from sense_pulse.context import AppContext
from sense_pulse.datasources.base import SensorReading
from sense_pulse.web.app import create_app, get_context
from tests.mock_datasource import MockDataSource


class TestWebAppCreation:
    """Test web app creation with and without context."""

    def test_create_app_without_context(self):
        """Test app can be created without context."""
        app = create_app(context=None)

        assert app is not None
        assert app.state.context is None

    @pytest.mark.asyncio
    async def test_create_app_with_context(self):
        """Test app receives injected context."""
        config = Config()
        context = AppContext.create(config, poll_interval=10.0)
        source = MockDataSource(source_id="test")
        context.add_data_source(source)

        await context.start()

        try:
            app = create_app(context=context)

            assert app.state.context is context
        finally:
            await context.shutdown()

    @pytest.mark.asyncio
    async def test_health_endpoint_with_context(self):
        """Test health endpoint works with injected context."""
        config = Config()
        context = AppContext.create(config, poll_interval=10.0)
        await context.start()

        try:
            app = create_app(context=context)
            client = TestClient(app)

            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
        finally:
            await context.shutdown()

    @pytest.mark.asyncio
    async def test_sensors_endpoint_uses_context_cache(self):
        """Test /api/sensors uses cache from context (no auth required)."""
        config = Config()
        context = AppContext.create(config, poll_interval=10.0)

        # Add mock source with test data
        readings = [
            SensorReading("temperature", 22.5, "°C", datetime.now()),
            SensorReading("humidity", 45.0, "%", datetime.now()),
        ]
        source = MockDataSource(source_id="sensors", readings=readings)
        context.add_data_source(source)

        await context.start()

        try:
            app = create_app(context=context)
            client = TestClient(app)

            # Give cache time to populate
            import asyncio

            await asyncio.sleep(0.2)

            response = client.get("/api/sensors")

            assert response.status_code == 200
            data = response.json()
            # Data should come from the mock source via context cache
            assert isinstance(data, dict)
        finally:
            await context.shutdown()


class TestGetContextDependency:
    """Test get_context dependency function."""

    @pytest.mark.asyncio
    async def test_get_context_returns_context_from_app_state(self):
        """Test get_context returns context from request.app.state."""
        config = Config()
        context = AppContext.create(config, poll_interval=10.0)
        await context.start()

        try:
            app = create_app(context=context)

            # Create a mock request with the app
            class MockRequest:
                def __init__(self, app):
                    self.app = app

            mock_request = MockRequest(app)

            result = get_context(mock_request)  # type: ignore
            assert result is context
        finally:
            await context.shutdown()

    def test_get_context_raises_when_no_context(self):
        """Test get_context raises RuntimeError when context is not set."""
        app = create_app(context=None)

        class MockRequest:
            def __init__(self, app):
                self.app = app

        mock_request = MockRequest(app)

        with pytest.raises(RuntimeError, match="AppContext not initialized"):
            get_context(mock_request)  # type: ignore

    @pytest.mark.asyncio
    async def test_context_accessible_via_depends_in_route(self):
        """Test that context is accessible in routes via Depends."""
        config = Config()
        context = AppContext.create(config, poll_interval=10.0)
        await context.start()

        try:
            app = create_app(context=context)
            client = TestClient(app)

            # The /api/datasources/status endpoint uses Depends(get_context)
            response = client.get("/api/datasources/status")

            assert response.status_code == 200
            # Should return a list of data source statuses
            assert isinstance(response.json(), list)
        finally:
            await context.shutdown()
