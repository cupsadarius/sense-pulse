"""Main controller for stats display"""

import asyncio
import contextlib
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sense_pulse.cache import DataCache

from sense_pulse.config import Config
from sense_pulse.devices.display import SenseHatDisplay
from sense_pulse.pi_leds import disable_all_leds, enable_all_leds
from sense_pulse.schedule import SleepSchedule
from sense_pulse.web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="display")


class StatsDisplay:
    """Main controller for displaying stats on Sense HAT"""

    def __init__(
        self,
        config: Config,
        cache: "DataCache",
        sense_hat_instance=None,
    ):
        """
        Initialize the stats display controller.

        Args:
            config: Application configuration
            cache: DataCache instance for accessing sensor data
            sense_hat_instance: Optional SenseHat hardware instance
        """
        logger.info(
            "Initializing StatsDisplay",
            show_icons=config.display.show_icons,
            rotation=config.display.rotation,
        )

        self.config = config
        self.cache = cache
        self.show_icons = config.display.show_icons
        self.display: Optional[SenseHatDisplay] = None  # Will be initialized in async_init()
        self._sense_hat_instance = sense_hat_instance

        self.sleep_schedule = SleepSchedule(
            config.sleep.start_hour,
            config.sleep.end_hour,
        )

        # Track sleep state for Pi LED control
        self._was_sleeping = False
        self._disable_pi_leds = config.sleep.disable_pi_leds

        logger.info("StatsDisplay initialized")

    async def async_init(self) -> None:
        """Complete async initialization (call this after __init__)"""
        # Initialize display with SenseHat instance
        self.display = SenseHatDisplay(
            sense_hat_instance=self._sense_hat_instance,
            rotation=self.config.display.rotation,
            scroll_speed=self.config.display.scroll_speed,
            icon_duration=self.config.display.icon_duration,
        )

        logger.info("StatsDisplay async initialization completed")

    async def display_tailscale_status(self):
        """Display Tailscale connection status and device count (from cache)"""
        assert self.display is not None  # Guaranteed by async_init()
        status = await self.cache.get("tailscale", {})

        is_connected = status.get("connected", {}).get("value", False)
        device_count = status.get("device_count", {}).get("value", 0)
        logger.info(
            "Displaying Tailscale",
            connected=is_connected,
            device_count=device_count,
        )

        if self.show_icons:
            icon_name = "tailscale_connected" if is_connected else "tailscale_disconnected"
            status_text = "Connected" if is_connected else "Disconnected"
            color = (0, 255, 0) if is_connected else (255, 0, 0)
            await self.display.show_icon_with_text(icon_name, status_text, text_color=color)
        else:
            status_text = "TS: Connected" if is_connected else "TS: Disconnected"
            color = (0, 255, 0) if is_connected else (255, 0, 0)
            await self.display.show_text(status_text, color=color)

        if is_connected:
            if self.show_icons:
                await self.display.show_icon_with_text(
                    "devices",
                    f"{device_count} Devices",
                    text_color=(0, 200, 255),
                )
            else:
                await self.display.show_text(
                    f"TS Devices: {device_count}",
                    color=(0, 200, 255),
                )

    async def display_pihole_stats(self):
        """Display Pi-hole statistics (from cache)"""
        assert self.display is not None  # Guaranteed by async_init()
        stats = await self.cache.get("pihole", {})

        queries_today = stats.get("queries_today", {}).get("value", 0)
        ads_blocked_today = stats.get("ads_blocked_today", {}).get("value", 0)
        ads_percentage_today = stats.get("ads_percentage_today", {}).get("value", 0.0)

        logger.info(
            "Displaying Pi-hole",
            queries=queries_today,
            blocked=ads_blocked_today,
            block_percent=round(ads_percentage_today, 1),
        )

        if self.show_icons:
            await self.display.show_icon_with_text(
                "query",
                f"Queries: {queries_today}",
                text_color=(0, 255, 0),
            )
            await self.display.show_icon_with_text(
                "block",
                f"Blocked: {ads_blocked_today}",
                text_color=(255, 0, 0),
            )
            await self.display.show_icon_with_text(
                "pihole_shield",
                f"{ads_percentage_today:.1f}% Blocked",
                text_color=(255, 165, 0),
            )
        else:
            await self.display.show_text(
                f"Queries: {queries_today}",
                color=(0, 255, 0),
            )
            await self.display.show_text(
                f"Blocked: {ads_blocked_today}",
                color=(255, 0, 0),
            )
            await self.display.show_text(
                f"Block%: {ads_percentage_today:.1f}%",
                color=(255, 165, 0),
            )

    async def display_sensor_data(self):
        """Display Sense HAT sensor data (from cache)"""
        assert self.display is not None  # Guaranteed by async_init()
        sensors = await self.cache.get("sensors", {})

        temperature = sensors.get("temperature", {}).get("value", 0.0)
        humidity = sensors.get("humidity", {}).get("value", 0.0)
        pressure = sensors.get("pressure", {}).get("value", 0.0)

        logger.info(
            "Displaying SenseHAT sensors",
            temperature=round(temperature, 1),
            humidity=round(humidity, 1),
            pressure=round(pressure, 0),
        )

        if self.show_icons:
            await self.display.show_icon_with_text(
                "thermometer",
                f"{temperature:.1f}C",
                text_color=(255, 100, 0),
            )
            await self.display.show_icon_with_text(
                "water_drop",
                f"{humidity:.1f}%",
                text_color=(0, 100, 255),
            )
            await self.display.show_icon_with_text(
                "pressure_gauge",
                f"{pressure:.0f}mb",
                text_color=(200, 200, 200),
            )
        else:
            await self.display.show_text(
                f"Temp: {temperature:.1f}C",
                color=(255, 100, 0),
            )
            await self.display.show_text(
                f"Humid: {humidity:.1f}%",
                color=(0, 100, 255),
            )
            await self.display.show_text(
                f"Press: {pressure:.0f}mb",
                color=(200, 200, 200),
            )

    async def display_system_stats(self):
        """Display system resource statistics (from cache)"""
        assert self.display is not None  # Guaranteed by async_init()
        stats = await self.cache.get("system", {})

        cpu_percent = stats.get("cpu_percent", {}).get("value", 0.0)
        memory_percent = stats.get("memory_percent", {}).get("value", 0.0)
        load_1min = stats.get("load_1min", {}).get("value", 0.0)

        logger.info(
            "Displaying system stats",
            cpu_percent=round(cpu_percent, 0),
            memory_percent=round(memory_percent, 0),
            load_1min=round(load_1min, 2),
        )

        if self.show_icons:
            await self.display.show_icon_with_text(
                "cpu",
                f"CPU: {cpu_percent:.0f}%",
                text_color=(255, 200, 0),
            )
            await self.display.show_icon_with_text(
                "memory",
                f"Mem: {memory_percent:.0f}%",
                text_color=(0, 200, 255),
            )
            await self.display.show_icon_with_text(
                "load",
                f"Load: {load_1min:.2f}",
                text_color=(255, 0, 255),
            )
        else:
            await self.display.show_text(
                f"CPU: {cpu_percent:.0f}%",
                color=(255, 200, 0),
            )
            await self.display.show_text(
                f"Mem: {memory_percent:.0f}%",
                color=(0, 200, 255),
            )
            await self.display.show_text(
                f"Load: {load_1min:.2f}",
                color=(255, 0, 255),
            )

    def _get_co2_color(self, co2: int) -> tuple:
        """Get color based on CO2 level (green/yellow/red)"""
        if co2 < 1000:
            return (0, 255, 0)  # Green - good
        elif co2 < 1500:
            return (255, 255, 0)  # Yellow - moderate
        else:
            return (255, 0, 0)  # Red - poor

    def _get_co2_icon(self, co2: int) -> str:
        """Get icon name based on CO2 level"""
        if co2 < 1000:
            return "co2_good"
        elif co2 < 1500:
            return "co2_moderate"
        else:
            return "co2_poor"

    async def display_co2_levels(self):
        """Display Aranet4 sensor data (temperature, CO2, humidity) from cache"""
        assert self.display is not None  # Guaranteed by async_init()
        co2_data = await self.cache.get("co2", {})
        if not co2_data:
            return

        # Display all sensors dynamically
        for sensor_label, sensor_data in co2_data.items():
            # Skip the 'available' key if present
            if sensor_label == "available" or not isinstance(sensor_data, dict):
                continue

            # Extract sensor readings from nested value structure
            value_data = sensor_data.get("value", {})
            temperature = value_data.get("temperature")
            co2 = value_data.get("co2")
            humidity = value_data.get("humidity")

            logger.info(
                "Displaying Aranet4 sensor",
                sensor=sensor_label,
                co2=co2,
                temperature=temperature,
                humidity=humidity,
            )

            # Display temperature
            if temperature is not None:
                if self.show_icons:
                    await self.display.show_icon_with_text(
                        "thermometer",
                        f"{sensor_label}: {temperature}°C",
                        text_color=(255, 100, 0),
                    )
                else:
                    await self.display.show_text(
                        f"{sensor_label} Temp: {temperature}°C",
                        color=(255, 100, 0),
                    )

            # Display CO2
            if co2 is not None:
                color = self._get_co2_color(co2)
                if self.show_icons:
                    icon = self._get_co2_icon(co2)
                    await self.display.show_icon_with_text(
                        icon,
                        f"{sensor_label}: {co2}ppm",
                        text_color=color,
                    )
                else:
                    await self.display.show_text(
                        f"{sensor_label} CO2: {co2}ppm",
                        color=color,
                    )

            # Display humidity
            if humidity is not None:
                if self.show_icons:
                    await self.display.show_icon_with_text(
                        "water_drop",
                        f"{sensor_label}: {humidity}%",
                        text_color=(0, 100, 255),
                    )
                else:
                    await self.display.show_text(
                        f"{sensor_label} Humidity: {humidity}%",
                        color=(0, 100, 255),
                    )

    def _get_weather_icon(self, conditions: str) -> str:
        """
        Map weather conditions to icon name.

        Args:
            conditions: Weather condition string from wttr.in (e.g., "Sunny", "Partly cloudy")

        Returns:
            Icon name for the weather condition
        """
        conditions_lower = conditions.lower()

        # Map common weather conditions to icons
        if any(word in conditions_lower for word in ["clear", "sunny"]):
            return "sunny"
        elif any(word in conditions_lower for word in ["partly cloudy", "partly"]):
            return "partly_cloudy"
        elif any(word in conditions_lower for word in ["overcast", "cloudy", "cloud"]):
            return "cloudy"
        elif any(word in conditions_lower for word in ["thunder", "thunderstorm", "lightning"]):
            return "thunderstorm"
        elif any(word in conditions_lower for word in ["rain", "drizzle", "shower"]):
            return "rainy"
        elif any(word in conditions_lower for word in ["snow", "sleet", "blizzard"]):
            return "snowy"
        elif any(word in conditions_lower for word in ["mist", "fog", "haze"]):
            return "mist"
        else:
            # Default to cloudy for unknown conditions
            return "cloudy"

    async def display_weather(self):
        """Display current weather conditions (from cache)"""
        assert self.display is not None  # Guaranteed by async_init()
        if not self.config.weather.enabled:
            return

        weather_data = await self.cache.get("weather", {})
        if not weather_data or "weather_temp" not in weather_data:
            logger.debug("No weather data available")
            return

        # Extract weather data from nested value structure
        temperature = weather_data.get("weather_temp", {}).get("value")
        conditions = weather_data.get("weather_conditions", {}).get("value", "Unknown")
        location = weather_data.get("weather_location", {}).get("value", "")

        logger.info(
            "Displaying weather",
            location=location,
            temperature=temperature,
            conditions=conditions,
        )

        # Display temperature with weather icon
        if temperature is not None:
            icon = self._get_weather_icon(conditions)
            if self.show_icons:
                await self.display.show_icon_with_text(
                    icon,
                    f"{temperature:.0f}°C",
                    text_color=(255, 200, 0),
                )
            else:
                await self.display.show_text(
                    f"Weather: {temperature:.0f}°C",
                    color=(255, 200, 0),
                )

        # Display weather conditions
        if conditions and conditions != "Unknown":
            if self.show_icons:
                # Show conditions with location if available
                text = f"{conditions}"
                if location:
                    text = f"{location}: {conditions}"
                await self.display.show_text(text, color=(100, 200, 255))
            else:
                await self.display.show_text(
                    f"Conditions: {conditions}",
                    color=(100, 200, 255),
                )

    async def run_cycle(self):
        """Run one complete display cycle"""
        assert self.display is not None  # Guaranteed by async_init()
        is_sleeping = self.sleep_schedule.is_sleep_time()

        # Handle sleep state transitions for Pi LED control
        if self._disable_pi_leds:
            if is_sleeping and not self._was_sleeping:
                # Entering sleep mode - disable Pi LEDs
                logger.info("Entering sleep mode", action="disable_leds")
                disable_all_leds()
            elif not is_sleeping and self._was_sleeping:
                # Exiting sleep mode - re-enable Pi LEDs
                logger.info("Exiting sleep mode", action="enable_leds")
                enable_all_leds()

        self._was_sleeping = is_sleeping

        if is_sleeping:
            logger.debug("Sleep time - display off")
            await self.display.clear()
            return

        logger.info("Starting display cycle")

        try:
            await self.display_tailscale_status()
            await self.display_pihole_stats()
            await self.display_sensor_data()
            await self.display_weather()
            await self.display_co2_levels()
            await self.display_system_stats()
            logger.info("Display cycle completed", status="ok")
        except Exception as e:
            logger.error("Display cycle failed", error=str(e), exc_info=True)
            await self.display.clear()

    async def run_until_shutdown(
        self, shutdown_event: asyncio.Event, interval: Optional[int] = None
    ):
        """
        Run continuous display loop until shutdown event is set.

        Args:
            shutdown_event: Event that signals shutdown when set
            interval: Update interval in seconds (uses config default if not specified)
        """
        assert self.display is not None  # Guaranteed by async_init()
        update_interval = interval or self.config.update.interval
        logger.info("Starting continuous display", interval=update_interval)

        try:
            while not shutdown_event.is_set():
                await self.run_cycle()
                logger.debug("Waiting before next cycle", wait_seconds=update_interval)
                # Wait for either the interval or shutdown signal
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(shutdown_event.wait(), timeout=update_interval)
        except asyncio.CancelledError:
            logger.info("Display loop cancelled")
            raise  # Re-raise so finally block runs, then caller handles it
        except Exception as e:
            logger.error("Fatal error in continuous loop", error=str(e), exc_info=True)
            raise
        finally:
            logger.info("Cleaning up display")
            await self.display.clear()
            # Re-enable Pi LEDs on shutdown if they were managed
            if self._disable_pi_leds and self._was_sleeping:
                logger.info("Re-enabling Pi LEDs on shutdown")
                enable_all_leds()

    async def run_continuous(self, interval: Optional[int] = None):
        """
        Run continuous display loop (legacy method).

        Note: Prefer run_until_shutdown() for proper signal handling.
        """
        # Create a local shutdown event that's never set for backwards compatibility
        shutdown_event = asyncio.Event()
        await self.run_until_shutdown(shutdown_event, interval)
