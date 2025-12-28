"""Main controller for stats display"""

import logging
import time
from typing import Optional

from sense_pulse.config import Config
from sense_pulse.display import SenseHatDisplay
from sense_pulse.pi_leds import disable_all_leds, enable_all_leds
from sense_pulse.pihole import PiHoleStats
from sense_pulse.schedule import SleepSchedule
from sense_pulse.system import SystemStats
from sense_pulse.tailscale import TailscaleStatus

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

        self.pihole = PiHoleStats(config.pihole.host, config.pihole.password)
        self.tailscale = TailscaleStatus(config.tailscale.cache_duration)
        self.display = SenseHatDisplay(
            rotation=config.display.rotation,
            scroll_speed=config.display.scroll_speed,
            icon_duration=config.display.icon_duration,
        )
        self.sleep_schedule = SleepSchedule(
            config.sleep.start_hour,
            config.sleep.end_hour,
        )
        self.system = SystemStats()

        # Track sleep state for Pi LED control
        self._was_sleeping = False
        self._disable_pi_leds = config.sleep.disable_pi_leds

        logger.info("StatsDisplay initialized successfully")

    def display_tailscale_status(self):
        """Display Tailscale connection status and device count"""
        logger.info("Displaying Tailscale status...")
        status = self.tailscale.get_status_summary()

        is_connected = status["connected"]

        if self.show_icons:
            icon_name = "tailscale_connected" if is_connected else "tailscale_disconnected"
            status_text = "Connected" if is_connected else "Disconnected"
            color = (0, 255, 0) if is_connected else (255, 0, 0)
            self.display.show_icon_with_text(icon_name, status_text, text_color=color)
        else:
            status_text = "TS: Connected" if is_connected else "TS: Disconnected"
            color = (0, 255, 0) if is_connected else (255, 0, 0)
            self.display.show_text(status_text, color=color)

        if is_connected:
            device_count = status["device_count"]
            if self.show_icons:
                self.display.show_icon_with_text(
                    "devices",
                    f"{device_count} Devices",
                    text_color=(0, 200, 255),
                )
            else:
                self.display.show_text(
                    f"TS Devices: {device_count}",
                    color=(0, 200, 255),
                )

    def display_pihole_stats(self):
        """Display Pi-hole statistics"""
        logger.info("Displaying Pi-hole stats...")
        stats = self.pihole.get_summary()

        if self.show_icons:
            self.display.show_icon_with_text(
                "query",
                f"Queries: {stats['queries_today']}",
                text_color=(0, 255, 0),
            )
            self.display.show_icon_with_text(
                "block",
                f"Blocked: {stats['ads_blocked_today']}",
                text_color=(255, 0, 0),
            )
            self.display.show_icon_with_text(
                "pihole_shield",
                f"{stats['ads_percentage_today']:.1f}% Blocked",
                text_color=(255, 165, 0),
            )
        else:
            self.display.show_text(
                f"Queries: {stats['queries_today']}",
                color=(0, 255, 0),
            )
            self.display.show_text(
                f"Blocked: {stats['ads_blocked_today']}",
                color=(255, 0, 0),
            )
            self.display.show_text(
                f"Block%: {stats['ads_percentage_today']:.1f}%",
                color=(255, 165, 0),
            )

    def display_sensor_data(self):
        """Display Sense HAT sensor data"""
        logger.info("Displaying sensor data...")
        sensors = self.display.get_sensor_data()

        if self.show_icons:
            self.display.show_icon_with_text(
                "thermometer",
                f"{sensors['temperature']:.1f}C",
                text_color=(255, 100, 0),
            )
            self.display.show_icon_with_text(
                "water_drop",
                f"{sensors['humidity']:.1f}%",
                text_color=(0, 100, 255),
            )
            self.display.show_icon_with_text(
                "pressure_gauge",
                f"{sensors['pressure']:.0f}mb",
                text_color=(200, 200, 200),
            )
        else:
            self.display.show_text(
                f"Temp: {sensors['temperature']:.1f}C",
                color=(255, 100, 0),
            )
            self.display.show_text(
                f"Humid: {sensors['humidity']:.1f}%",
                color=(0, 100, 255),
            )
            self.display.show_text(
                f"Press: {sensors['pressure']:.0f}mb",
                color=(200, 200, 200),
            )

    def display_system_stats(self):
        """Display system resource statistics"""
        logger.info("Displaying system stats...")
        stats = self.system.get_stats()

        if self.show_icons:
            self.display.show_icon_with_text(
                "cpu",
                f"CPU: {stats['cpu_percent']:.0f}%",
                text_color=(255, 200, 0),
            )
            self.display.show_icon_with_text(
                "memory",
                f"Mem: {stats['memory_percent']:.0f}%",
                text_color=(0, 200, 255),
            )
            self.display.show_icon_with_text(
                "load",
                f"Load: {stats['load_1min']:.2f}",
                text_color=(255, 0, 255),
            )
        else:
            self.display.show_text(
                f"CPU: {stats['cpu_percent']:.0f}%",
                color=(255, 200, 0),
            )
            self.display.show_text(
                f"Mem: {stats['memory_percent']:.0f}%",
                color=(0, 200, 255),
            )
            self.display.show_text(
                f"Load: {stats['load_1min']:.2f}",
                color=(255, 0, 255),
            )

    def run_cycle(self):
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
            self.display.clear()
            return

        logger.info("Starting display cycle...")

        try:
            self.display_tailscale_status()
            self.display_pihole_stats()
            self.display_sensor_data()
            self.display_system_stats()
            logger.info("Display cycle completed successfully")
        except Exception as e:
            logger.error(f"Error during display cycle: {e}")
            self.display.clear()

    def run_continuous(self, interval: Optional[int] = None):
        """Run continuous display loop"""
        update_interval = interval or self.config.update.interval
        logger.info(f"Starting continuous display with {update_interval}s interval...")

        try:
            while True:
                self.run_cycle()
                logger.debug(f"Waiting {update_interval} seconds before next cycle...")
                time.sleep(update_interval)
        except KeyboardInterrupt:
            logger.info("Received shutdown signal, cleaning up...")
            self.display.clear()
            # Re-enable Pi LEDs on shutdown if they were managed
            if self._disable_pi_leds and self._was_sleeping:
                logger.info("Re-enabling Pi onboard LEDs on shutdown")
                enable_all_leds()
            logger.info("Shutdown complete")
        except Exception as e:
            logger.error(f"Fatal error in continuous loop: {e}")
            self.display.clear()
            raise
