"""Main controller for stats display"""

import asyncio
import contextlib
import logging
from typing import Optional

from sense_pulse.cache import get_cache
from sense_pulse.config import Config
from sense_pulse.devices.display import SenseHatDisplay
from sense_pulse.pi_leds import disable_all_leds, enable_all_leds
from sense_pulse.schedule import SleepSchedule

logger = logging.getLogger(__name__)


class StatsDisplay:
    """Main controller for displaying stats on Sense HAT"""

    def __init__(self, config: Config):
        """
        Initialize the stats display controller.

        Args:
            config: Application configuration
        """
        logger.info("Initializing StatsDisplay...")

        self.config = config
        self.show_icons = config.display.show_icons
        self.cache = None  # Will be initialized in async_init()

        self.display = SenseHatDisplay(
            rotation=config.display.rotation,
            scroll_speed=config.display.scroll_speed,
            icon_duration=config.display.icon_duration,
        )
        self.sleep_schedule = SleepSchedule(
            config.sleep.start_hour,
            config.sleep.end_hour,
        )

        # Track sleep state for Pi LED control
        self._was_sleeping = False
        self._disable_pi_leds = config.sleep.disable_pi_leds

        logger.info("StatsDisplay initialized (async_init required)")

    async def async_init(self) -> None:
        """Complete async initialization (call this after __init__)"""
        # Get global cache instance (already initialized by CLI with data sources)
        self.cache = await get_cache()
        logger.info("StatsDisplay async initialization completed")

    async def display_tailscale_status(self):
        """Display Tailscale connection status and device count (from cache)"""
        logger.info("Displaying Tailscale status...")
        status = await self.cache.get("tailscale", {})

        is_connected = status["connected"]

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
            device_count = status["device_count"]
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
        logger.info("Displaying Pi-hole stats...")
        stats = await self.cache.get("pihole", {})

        if self.show_icons:
            await self.display.show_icon_with_text(
                "query",
                f"Queries: {stats['queries_today']}",
                text_color=(0, 255, 0),
            )
            await self.display.show_icon_with_text(
                "block",
                f"Blocked: {stats['ads_blocked_today']}",
                text_color=(255, 0, 0),
            )
            await self.display.show_icon_with_text(
                "pihole_shield",
                f"{stats['ads_percentage_today']:.1f}% Blocked",
                text_color=(255, 165, 0),
            )
        else:
            await self.display.show_text(
                f"Queries: {stats['queries_today']}",
                color=(0, 255, 0),
            )
            await self.display.show_text(
                f"Blocked: {stats['ads_blocked_today']}",
                color=(255, 0, 0),
            )
            await self.display.show_text(
                f"Block%: {stats['ads_percentage_today']:.1f}%",
                color=(255, 165, 0),
            )

    async def display_sensor_data(self):
        """Display Sense HAT sensor data (from cache)"""
        logger.info("Displaying sensor data...")
        sensors = await self.cache.get("sensors", {})

        if self.show_icons:
            await self.display.show_icon_with_text(
                "thermometer",
                f"{sensors['temperature']:.1f}C",
                text_color=(255, 100, 0),
            )
            await self.display.show_icon_with_text(
                "water_drop",
                f"{sensors['humidity']:.1f}%",
                text_color=(0, 100, 255),
            )
            await self.display.show_icon_with_text(
                "pressure_gauge",
                f"{sensors['pressure']:.0f}mb",
                text_color=(200, 200, 200),
            )
        else:
            await self.display.show_text(
                f"Temp: {sensors['temperature']:.1f}C",
                color=(255, 100, 0),
            )
            await self.display.show_text(
                f"Humid: {sensors['humidity']:.1f}%",
                color=(0, 100, 255),
            )
            await self.display.show_text(
                f"Press: {sensors['pressure']:.0f}mb",
                color=(200, 200, 200),
            )

    async def display_system_stats(self):
        """Display system resource statistics (from cache)"""
        logger.info("Displaying system stats...")
        stats = await self.cache.get("system", {})

        if self.show_icons:
            await self.display.show_icon_with_text(
                "cpu",
                f"CPU: {stats['cpu_percent']:.0f}%",
                text_color=(255, 200, 0),
            )
            await self.display.show_icon_with_text(
                "memory",
                f"Mem: {stats['memory_percent']:.0f}%",
                text_color=(0, 200, 255),
            )
            await self.display.show_icon_with_text(
                "load",
                f"Load: {stats['load_1min']:.2f}",
                text_color=(255, 0, 255),
            )
        else:
            await self.display.show_text(
                f"CPU: {stats['cpu_percent']:.0f}%",
                color=(255, 200, 0),
            )
            await self.display.show_text(
                f"Mem: {stats['memory_percent']:.0f}%",
                color=(0, 200, 255),
            )
            await self.display.show_text(
                f"Load: {stats['load_1min']:.2f}",
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
        co2_data = await self.cache.get("co2", {})
        if not co2_data:
            return

        logger.info("Displaying Aranet4 sensor data...")

        # Display all sensors dynamically
        for sensor_label, sensor_data in co2_data.items():
            # Skip the 'available' key if present
            if sensor_label == "available" or not isinstance(sensor_data, dict):
                continue

            # Extract sensor readings
            temperature = sensor_data.get("temperature")
            co2 = sensor_data.get("co2")
            humidity = sensor_data.get("humidity")

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

    async def run_cycle(self):
        """Run one complete display cycle"""
        is_sleeping = self.sleep_schedule.is_sleep_time()

        # Handle sleep state transitions for Pi LED control
        if self._disable_pi_leds:
            if is_sleeping and not self._was_sleeping:
                # Entering sleep mode - disable Pi LEDs
                logger.info("Entering sleep mode - disabling Pi onboard LEDs")
                disable_all_leds()
            elif not is_sleeping and self._was_sleeping:
                # Exiting sleep mode - re-enable Pi LEDs
                logger.info("Exiting sleep mode - re-enabling Pi onboard LEDs")
                enable_all_leds()

        self._was_sleeping = is_sleeping

        if is_sleeping:
            logger.info("Sleep time - display off")
            await self.display.clear()
            return

        logger.info("Starting display cycle...")

        try:
            await self.display_tailscale_status()
            await self.display_pihole_stats()
            await self.display_sensor_data()
            await self.display_co2_levels()
            await self.display_system_stats()
            logger.info("Display cycle completed successfully")
        except Exception as e:
            logger.error(f"Error during display cycle: {e}")
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
        update_interval = interval or self.config.update.interval
        logger.info(f"Starting continuous display with {update_interval}s interval...")

        try:
            while not shutdown_event.is_set():
                await self.run_cycle()
                logger.debug(f"Waiting {update_interval} seconds before next cycle...")
                # Wait for either the interval or shutdown signal
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(shutdown_event.wait(), timeout=update_interval)
        except asyncio.CancelledError:
            logger.info("Display loop cancelled by signal")
            raise  # Re-raise so finally block runs, then caller handles it
        except Exception as e:
            logger.error(f"Fatal error in continuous loop: {e}")
            raise
        finally:
            logger.info("Cleaning up display...")
            await self.display.clear()
            # Re-enable Pi LEDs on shutdown if they were managed
            if self._disable_pi_leds and self._was_sleeping:
                logger.info("Re-enabling Pi onboard LEDs on shutdown")
                enable_all_leds()

    async def run_continuous(self, interval: Optional[int] = None):
        """
        Run continuous display loop (legacy method).

        Note: Prefer run_until_shutdown() for proper signal handling.
        """
        # Create a local shutdown event that's never set for backwards compatibility
        shutdown_event = asyncio.Event()
        await self.run_until_shutdown(shutdown_event, interval)
