"""Sense HAT LED display and sensor handling"""

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sense_hat import SenseHat

from sense_pulse import hardware, icons

logger = logging.getLogger(__name__)


class SenseHatDisplay:
    """Handles Sense HAT sensor reading and LED display"""

    def __init__(
        self,
        rotation: int = 0,
        scroll_speed: float = 0.08,
        icon_duration: float = 1.5,
    ):
        """
        Initialize Sense HAT display.

        Args:
            rotation: Display rotation (0, 90, 180, 270)
            scroll_speed: Text scroll speed
            icon_duration: Default icon display duration
        """
        try:
            # Use shared SenseHat instance from hardware module
            self.sense: Optional[SenseHat] = hardware.get_sense_hat()
            if self.sense is None:
                raise RuntimeError("Sense HAT not available")
            hardware._set_rotation_sync(rotation)
            self.sense.low_light = True
            self.scroll_speed = scroll_speed
            self.icon_duration = icon_duration
            logger.info(f"Initialized Sense HAT with rotation: {rotation}")
        except Exception as e:
            logger.error(f"Failed to initialize Sense HAT: {e}")
            raise

    def get_sensor_data(self) -> dict[str, float]:
        """Read all sensor data from Sense HAT"""
        try:
            temp = self.sense.get_temperature()
            humidity = self.sense.get_humidity()
            pressure = self.sense.get_pressure()

            logger.debug(
                f"Sensor readings - Temp: {temp:.1f}C, "
                f"Humidity: {humidity:.1f}%, Pressure: {pressure:.1f}mb"
            )

            return {
                "temperature": round(temp, 1),
                "humidity": round(humidity, 1),
                "pressure": round(pressure, 1),
            }
        except Exception as e:
            logger.error(f"Failed to read sensor data: {e}")
            return {"temperature": 0, "humidity": 0, "pressure": 0}

    async def show_text(
        self,
        text: str,
        color: tuple[int, int, int] = (255, 255, 255),
        scroll_speed: Optional[float] = None,
    ):
        """Display scrolling text on LED matrix (async to prevent blocking)"""
        try:
            speed = scroll_speed if scroll_speed is not None else self.scroll_speed
            logger.debug(f"Displaying text: {text}")
            # Run blocking show_message in thread pool to prevent blocking event loop
            # This allows WebSocket to continue sending pixel updates during scrolling
            await asyncio.to_thread(
                self.sense.show_message, text, scroll_speed=speed, text_colour=color
            )
        except Exception as e:
            logger.error(f"Failed to display text: {e}")

    async def show_icon(
        self, icon_pixels: list[list[int]], duration: Optional[float] = None, mode: str = "icon"
    ):
        """
        Display an 8x8 icon on the LED matrix.

        Args:
            icon_pixels: 64-element list of [R,G,B] values
            duration: How long to display the icon in seconds
            mode: Display mode label for tracking
        """
        try:
            display_time = duration if duration is not None else self.icon_duration
            logger.debug("Displaying icon")
            # Use hardware module for matrix operations (handles state tracking)
            await hardware.set_pixels(icon_pixels, mode)
            await asyncio.sleep(display_time)
        except Exception as e:
            logger.error(f"Failed to display icon: {e}")

    async def show_icon_with_text(
        self,
        icon_name: str,
        text: str,
        text_color: tuple[int, int, int] = (255, 255, 255),
        icon_duration: Optional[float] = None,
        scroll_speed: Optional[float] = None,
    ):
        """
        Display an icon followed by scrolling text.

        Args:
            icon_name: Name of the icon to display
            text: Text to scroll after icon
            text_color: RGB color for text
            icon_duration: How long to show icon
            scroll_speed: Speed of text scrolling
        """
        icon = icons.get_icon(icon_name)
        if icon:
            await self.show_icon(icon, duration=icon_duration, mode=icon_name)
        # Update mode to show we're scrolling text
        hardware.set_display_mode("scrolling")
        await self.show_text(text, color=text_color, scroll_speed=scroll_speed)

    async def clear(self):
        """Clear the LED display"""
        try:
            # Use hardware module for matrix operations (handles state tracking)
            await hardware.clear_display()
        except Exception as e:
            logger.error(f"Failed to clear display: {e}")
