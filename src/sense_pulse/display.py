"""Sense HAT LED display and sensor handling"""

import logging
import time
from typing import Dict, List, Optional, Tuple

from sense_hat import SenseHat

from sense_pulse import icons

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
            self.sense = SenseHat()
            self.sense.set_rotation(rotation)
            self.sense.low_light = True
            self.scroll_speed = scroll_speed
            self.icon_duration = icon_duration
            logger.info(f"Initialized Sense HAT with rotation: {rotation}")
        except Exception as e:
            logger.error(f"Failed to initialize Sense HAT: {e}")
            raise

    def get_sensor_data(self) -> Dict[str, float]:
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

    def show_text(
        self,
        text: str,
        color: Tuple[int, int, int] = (255, 255, 255),
        scroll_speed: Optional[float] = None,
    ):
        """Display scrolling text on LED matrix"""
        try:
            speed = scroll_speed if scroll_speed is not None else self.scroll_speed
            logger.debug(f"Displaying text: {text}")
            self.sense.show_message(text, scroll_speed=speed, text_colour=color)
        except Exception as e:
            logger.error(f"Failed to display text: {e}")

    def show_icon(self, icon_pixels: List[List[int]], duration: Optional[float] = None):
        """
        Display an 8x8 icon on the LED matrix.

        Args:
            icon_pixels: 64-element list of [R,G,B] values
            duration: How long to display the icon in seconds
        """
        try:
            display_time = duration if duration is not None else self.icon_duration
            logger.debug("Displaying icon")
            self.sense.set_pixels(icon_pixels)
            time.sleep(display_time)
        except Exception as e:
            logger.error(f"Failed to display icon: {e}")

    def show_icon_with_text(
        self,
        icon_name: str,
        text: str,
        text_color: Tuple[int, int, int] = (255, 255, 255),
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
            self.show_icon(icon, duration=icon_duration)
        self.show_text(text, color=text_color, scroll_speed=scroll_speed)

    def clear(self):
        """Clear the LED display"""
        try:
            self.sense.clear()
        except Exception as e:
            logger.error(f"Failed to clear display: {e}")
