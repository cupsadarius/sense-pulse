"""Tests for display cycle controller."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sensehat.controller import DisplayController
from sensehat.display import SenseHatDisplay


@pytest.fixture
def mock_display() -> SenseHatDisplay:
    """Create a display with mocked methods."""
    display = SenseHatDisplay(sense_hat_instance=None)
    display.show_text = AsyncMock()
    display.show_icon = AsyncMock()
    display.show_icon_with_text = AsyncMock()
    display.clear = AsyncMock()
    return display


@pytest.fixture
def controller(mock_display: SenseHatDisplay) -> DisplayController:
    return DisplayController(display=mock_display, sleep_start=23, sleep_end=7)


def _fake_redis_with_sources(sources: dict) -> AsyncMock:
    """Create a mock Redis that returns the given sources from read_all_sources."""
    redis_mock = AsyncMock()
    return redis_mock


class TestDisplayControllerCycle:
    async def test_clears_display_during_sleep(self, controller: DisplayController) -> None:
        """Should clear display and skip cycle during sleep hours."""
        redis_mock = AsyncMock()

        with patch("sensehat.controller.is_sleep_time", return_value=True):
            await controller.run_cycle(redis_mock)

        controller.display.clear.assert_awaited_once()

    async def test_skips_sources_with_no_data(
        self, controller: DisplayController, mock_display: SenseHatDisplay
    ) -> None:
        """Should skip sources that have no data in Redis."""
        with (
            patch("sensehat.controller.is_sleep_time", return_value=False),
            patch("sensehat.controller.read_all_sources", new_callable=AsyncMock, return_value={}),
        ):
            await controller.run_cycle(AsyncMock())

        # No display methods should be called when there's no data
        mock_display.show_icon_with_text.assert_not_awaited()
        mock_display.show_text.assert_not_awaited()

    async def test_displays_tailscale_connected(
        self, controller: DisplayController, mock_display: SenseHatDisplay
    ) -> None:
        """Should show tailscale connected icon with device count."""
        all_data = {
            "tailscale": {
                "connected": {"value": True, "unit": None, "timestamp": 1.0},
                "device_count": {"value": 5, "unit": "devices", "timestamp": 1.0},
            }
        }

        with (
            patch("sensehat.controller.is_sleep_time", return_value=False),
            patch(
                "sensehat.controller.read_all_sources",
                new_callable=AsyncMock,
                return_value=all_data,
            ),
        ):
            await controller.run_cycle(AsyncMock())

        # Should show connected icon then device count
        calls = mock_display.show_icon_with_text.await_args_list
        assert len(calls) == 2
        assert calls[0].args[0] == "tailscale_connected"
        assert calls[1].args[0] == "devices"
        assert "5 Devices" in calls[1].args[1]

    async def test_displays_tailscale_disconnected(
        self, controller: DisplayController, mock_display: SenseHatDisplay
    ) -> None:
        """Should show disconnected icon when tailscale is down."""
        all_data = {
            "tailscale": {
                "connected": {"value": False, "unit": None, "timestamp": 1.0},
                "device_count": {"value": 0, "unit": "devices", "timestamp": 1.0},
            }
        }

        with (
            patch("sensehat.controller.is_sleep_time", return_value=False),
            patch(
                "sensehat.controller.read_all_sources",
                new_callable=AsyncMock,
                return_value=all_data,
            ),
        ):
            await controller.run_cycle(AsyncMock())

        calls = mock_display.show_icon_with_text.await_args_list
        assert calls[0].args[0] == "tailscale_disconnected"
        assert "Disconnected" in calls[0].args[1]

    async def test_displays_pihole_data(
        self, controller: DisplayController, mock_display: SenseHatDisplay
    ) -> None:
        """Should show pihole queries, blocked, and percentage."""
        all_data = {
            "pihole": {
                "queries_today": {"value": 12345, "unit": "queries", "timestamp": 1.0},
                "ads_blocked_today": {"value": 1234, "unit": "ads", "timestamp": 1.0},
                "ads_percentage_today": {"value": 10.0, "unit": "%", "timestamp": 1.0},
            }
        }

        with (
            patch("sensehat.controller.is_sleep_time", return_value=False),
            patch(
                "sensehat.controller.read_all_sources",
                new_callable=AsyncMock,
                return_value=all_data,
            ),
        ):
            await controller.run_cycle(AsyncMock())

        calls = mock_display.show_icon_with_text.await_args_list
        assert len(calls) == 3
        assert calls[0].args[0] == "query"
        assert calls[1].args[0] == "block"
        assert calls[2].args[0] == "pihole_shield"

    async def test_displays_system_data(
        self, controller: DisplayController, mock_display: SenseHatDisplay
    ) -> None:
        """Should show system CPU, memory, and load."""
        all_data = {
            "system": {
                "cpu_percent": {"value": 23.5, "unit": "%", "timestamp": 1.0},
                "memory_percent": {"value": 61.2, "unit": "%", "timestamp": 1.0},
                "load_1min": {"value": 1.23, "unit": "load", "timestamp": 1.0},
            }
        }

        with (
            patch("sensehat.controller.is_sleep_time", return_value=False),
            patch(
                "sensehat.controller.read_all_sources",
                new_callable=AsyncMock,
                return_value=all_data,
            ),
        ):
            await controller.run_cycle(AsyncMock())

        calls = mock_display.show_icon_with_text.await_args_list
        assert len(calls) == 3
        icons = [c.args[0] for c in calls]
        assert icons == ["cpu", "memory", "load"]

    async def test_displays_sensor_data(
        self, controller: DisplayController, mock_display: SenseHatDisplay
    ) -> None:
        """Should show sensor temp, humidity, and pressure."""
        all_data = {
            "sensors": {
                "temperature": {"value": 24.3, "unit": "C", "timestamp": 1.0},
                "humidity": {"value": 45.2, "unit": "%", "timestamp": 1.0},
                "pressure": {"value": 1013.2, "unit": "mbar", "timestamp": 1.0},
            }
        }

        with (
            patch("sensehat.controller.is_sleep_time", return_value=False),
            patch(
                "sensehat.controller.read_all_sources",
                new_callable=AsyncMock,
                return_value=all_data,
            ),
        ):
            await controller.run_cycle(AsyncMock())

        calls = mock_display.show_icon_with_text.await_args_list
        assert len(calls) == 3
        icons = [c.args[0] for c in calls]
        assert icons == ["thermometer", "water_drop", "pressure_gauge"]

    async def test_displays_weather_data(
        self, controller: DisplayController, mock_display: SenseHatDisplay
    ) -> None:
        """Should show weather icon and conditions text."""
        all_data = {
            "weather": {
                "weather_temp": {"value": 18.0, "unit": "C", "timestamp": 1.0},
                "weather_conditions": {"value": "Partly cloudy", "unit": None, "timestamp": 1.0},
                "weather_location": {"value": "London", "unit": None, "timestamp": 1.0},
            }
        }

        with (
            patch("sensehat.controller.is_sleep_time", return_value=False),
            patch(
                "sensehat.controller.read_all_sources",
                new_callable=AsyncMock,
                return_value=all_data,
            ),
        ):
            await controller.run_cycle(AsyncMock())

        icon_calls = mock_display.show_icon_with_text.await_args_list
        text_calls = mock_display.show_text.await_args_list
        # Weather shows icon_with_text for temp, then show_text for conditions
        assert len(icon_calls) == 1
        assert icon_calls[0].args[0] == "partly_cloudy"
        assert len(text_calls) == 1

    async def test_cycle_order(
        self, controller: DisplayController, mock_display: SenseHatDisplay
    ) -> None:
        """Sources should display in order: tailscale, pihole, system, sensors, co2, weather."""
        all_data = {
            "tailscale": {"connected": {"value": True}, "device_count": {"value": 3}},
            "pihole": {
                "queries_today": {"value": 100},
                "ads_blocked_today": {"value": 10},
                "ads_percentage_today": {"value": 10.0},
            },
            "system": {
                "cpu_percent": {"value": 50.0},
                "memory_percent": {"value": 60.0},
                "load_1min": {"value": 1.0},
            },
            "sensors": {
                "temperature": {"value": 22.0},
                "humidity": {"value": 50.0},
                "pressure": {"value": 1000.0},
            },
            "weather": {
                "weather_temp": {"value": 15.0},
                "weather_conditions": {"value": "Clear"},
                "weather_location": {"value": ""},
            },
        }

        call_order = []
        original_handlers = {
            "_show_tailscale": controller._show_tailscale,
            "_show_pihole": controller._show_pihole,
            "_show_system": controller._show_system,
            "_show_sensors": controller._show_sensors,
            "_show_co2": controller._show_co2,
            "_show_weather": controller._show_weather,
        }

        for name, handler in original_handlers.items():

            async def make_wrapper(n, h):
                async def wrapper(data):
                    call_order.append(n)
                    return await h(data)

                return wrapper

        # Use simpler approach: track which sources are displayed
        displayed_sources = []

        async def track_tailscale(data):
            displayed_sources.append("tailscale")

        async def track_pihole(data):
            displayed_sources.append("pihole")

        async def track_system(data):
            displayed_sources.append("system")

        async def track_sensors(data):
            displayed_sources.append("sensors")

        async def track_co2(data):
            displayed_sources.append("co2")

        async def track_weather(data):
            displayed_sources.append("weather")

        controller._show_tailscale = track_tailscale
        controller._show_pihole = track_pihole
        controller._show_system = track_system
        controller._show_sensors = track_sensors
        controller._show_co2 = track_co2
        controller._show_weather = track_weather

        with (
            patch("sensehat.controller.is_sleep_time", return_value=False),
            patch(
                "sensehat.controller.read_all_sources",
                new_callable=AsyncMock,
                return_value=all_data,
            ),
        ):
            await controller.run_cycle(AsyncMock())

        # CO2 is not in all_data, so it should be skipped
        assert displayed_sources == ["tailscale", "pihole", "system", "sensors", "weather"]

    async def test_handler_exception_doesnt_crash_cycle(
        self, controller: DisplayController, mock_display: SenseHatDisplay
    ) -> None:
        """An exception in one handler should not stop the cycle."""
        all_data = {
            "tailscale": {"connected": {"value": True}, "device_count": {"value": 1}},
            "sensors": {
                "temperature": {"value": 20.0},
                "humidity": {"value": 50.0},
                "pressure": {"value": 1000.0},
            },
        }

        # Make tailscale handler raise
        mock_display.show_icon_with_text.side_effect = [
            RuntimeError("display error"),  # tailscale call
            None,  # sensors calls
            None,
            None,
        ]

        with (
            patch("sensehat.controller.is_sleep_time", return_value=False),
            patch(
                "sensehat.controller.read_all_sources",
                new_callable=AsyncMock,
                return_value=all_data,
            ),
        ):
            # Should not raise
            await controller.run_cycle(AsyncMock())


class TestWeatherIconMapping:
    def test_clear_maps_to_sunny(self) -> None:
        assert DisplayController._weather_icon("Clear sky") == "sunny"

    def test_partly_cloudy(self) -> None:
        assert DisplayController._weather_icon("Partly cloudy") == "partly_cloudy"

    def test_overcast(self) -> None:
        assert DisplayController._weather_icon("Overcast") == "cloudy"

    def test_rain(self) -> None:
        assert DisplayController._weather_icon("Light rain") == "rainy"

    def test_snow(self) -> None:
        assert DisplayController._weather_icon("Heavy snow") == "snowy"

    def test_thunderstorm(self) -> None:
        assert DisplayController._weather_icon("Thunderstorm") == "thunderstorm"

    def test_mist(self) -> None:
        assert DisplayController._weather_icon("Mist") == "mist"

    def test_fog(self) -> None:
        assert DisplayController._weather_icon("Fog") == "mist"

    def test_unknown_defaults_to_cloudy(self) -> None:
        assert DisplayController._weather_icon("Unknown weather") == "cloudy"


class TestCO2IconMapping:
    def test_good_co2(self) -> None:
        assert DisplayController._co2_icon(450) == "co2_good"

    def test_moderate_co2(self) -> None:
        assert DisplayController._co2_icon(1200) == "co2_moderate"

    def test_poor_co2(self) -> None:
        assert DisplayController._co2_icon(1600) == "co2_poor"

    def test_boundary_1000(self) -> None:
        assert DisplayController._co2_icon(1000) == "co2_moderate"

    def test_boundary_1500(self) -> None:
        assert DisplayController._co2_icon(1500) == "co2_poor"

    def test_co2_color_good(self) -> None:
        assert DisplayController._co2_color(450) == (0, 255, 0)

    def test_co2_color_moderate(self) -> None:
        assert DisplayController._co2_color(1200) == (255, 255, 0)

    def test_co2_color_poor(self) -> None:
        assert DisplayController._co2_color(1600) == (255, 0, 0)
