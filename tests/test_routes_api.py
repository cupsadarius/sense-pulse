"""Tests for web routes API access patterns."""

import pytest

from sense_pulse.cache import DataCache


class MockAranet4Source:
    """Mock Aranet4 source with get_sensor_status method."""

    def get_metadata(self):
        from sense_pulse.datasources.base import DataSourceMetadata

        return DataSourceMetadata(
            source_id="co2",
            name="Mock Aranet4",
            description="Test Aranet4 source",
            refresh_interval=30,
        )

    def get_sensor_status(self):
        return {
            "Office": {
                "connected": True,
                "co2": 800,
                "temperature": 22.5,
                "humidity": 45,
            },
            "Bedroom": {
                "connected": False,
                "co2": None,
                "last_error": "Connection timeout",
            },
        }


class TestRoutesPublicAPIUsage:
    """Verify routes use public cache API, not private attributes."""

    @pytest.mark.asyncio
    async def test_aranet4_status_uses_public_api(self):
        """Verify _get_aranet4_status uses get_data_source_status."""
        cache = DataCache()
        mock_source = MockAranet4Source()

        # Register mock source
        cache._data_sources["co2"] = mock_source

        # Test public API returns status
        status = cache.get_data_source_status("co2")

        assert status is not None
        assert "Office" in status
        assert status["Office"]["co2"] == 800
        assert status["Office"]["connected"] is True
        assert "Bedroom" in status
        assert status["Bedroom"]["connected"] is False

    @pytest.mark.asyncio
    async def test_public_api_returns_none_for_missing_source(self):
        """Verify public API returns None for unregistered source."""
        cache = DataCache()

        status = cache.get_data_source_status("nonexistent")
        assert status is None

    @pytest.mark.asyncio
    async def test_list_sources_works(self):
        """Verify list_registered_sources returns correct IDs."""
        cache = DataCache()
        mock_source = MockAranet4Source()
        cache._data_sources["co2"] = mock_source

        sources = cache.list_registered_sources()
        assert "co2" in sources

    @pytest.mark.asyncio
    async def test_no_private_attribute_access_in_status_helper(self):
        """
        Ensure the updated _get_aranet4_status doesn't use _data_sources.

        This is a code review test - we verify by inspecting the implementation.
        """
        import inspect

        from sense_pulse.web.routes import _get_aranet4_status

        source_code = inspect.getsource(_get_aranet4_status)

        # Should NOT contain direct access to _data_sources
        assert (
            "_data_sources" not in source_code
        ), "_get_aranet4_status should use public API, not _data_sources"

        # Should use the public method
        assert (
            "get_data_source_status" in source_code
        ), "_get_aranet4_status should use get_data_source_status()"
