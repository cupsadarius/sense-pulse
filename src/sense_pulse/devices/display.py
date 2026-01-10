"""Sense HAT LED display handling - high-level wrapper"""

import asyncio
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sense_hat import SenseHat

from sense_pulse import icons
from sense_pulse.devices.sensehat_display import SenseHatDisplayController
from sense_pulse.web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="display")


class SenseHatDisplay:
    """
    High-level Sense HAT LED matrix display handler.

    Provides convenient methods for displaying text, icons, and combinations.
    Uses SenseHatDisplayController for state tracking and low-level operations.
    """

    def __init__(
        self,
        sense_hat_instance: Optional["SenseHat"] = None,
        display_controller: Optional[SenseHatDisplayController] = None,
        rotation: int = 0,
        scroll_speed: float = 0.08,
        icon_duration: float = 1.5,
    ):
        """
        Initialize Sense HAT display.

        Args:
            sense_hat_instance: Optional SenseHat hardware instance.
            display_controller: Optional display controller for state tracking.
                               If not provided, one will be created.
            rotation: Display rotation (0, 90, 180, 270)
            scroll_speed: Text scroll speed
            icon_duration: Default icon display duration
        """
        try:
            # Create or use provided display controller
            if display_controller is not None:
                self._controller = display_controller
                logger.info("Using provided display controller")
            elif sense_hat_instance is not None:
                self._controller = SenseHatDisplayController(sense_hat_instance)
                logger.info("Created display controller with provided SenseHat instance")
            else:
                # Fall back to lazy initialization
                self._controller = SenseHatDisplayController()
                logger.info("Created display controller with lazy initialization")

            # Get the sense hat instance from the controller
            self.sense: Optional[SenseHat] = self._controller.sense_hat

            if self.sense is None:
                raise RuntimeError("Sense HAT not available")

            # Set rotation on the actual instance and controller
            self.sense.set_rotation(rotation)
            self._controller.set_rotation_sync(rotation)
            self.sense.low_light = True
            self.scroll_speed = scroll_speed
            self.icon_duration = icon_duration

            logger.info(
                "Initialized Sense HAT display",
                rotation=rotation,
                scroll_speed=scroll_speed,
            )
        except Exception as e:
            logger.error("Failed to initialize Sense HAT display", error=str(e))
            raise

    @property
    def controller(self) -> SenseHatDisplayController:
        """Get the underlying display controller."""
        return self._controller

    async def show_text(
        self,
        text: str,
        color: tuple[int, int, int] = (255, 255, 255),
        scroll_speed: Optional[float] = None,
    ):
        """Display scrolling text on LED matrix (async to prevent blocking)"""
        try:
            speed = scroll_speed if scroll_speed is not None else self.scroll_speed
            logger.debug("Displaying text", text=text[:50] if len(text) > 50 else text)
            # Run blocking show_message in thread pool to prevent blocking event loop
            # This allows WebSocket to continue sending pixel updates during scrolling
            assert self.sense is not None  # Guaranteed by __init__
            await asyncio.to_thread(
                self.sense.show_message, text, scroll_speed=speed, text_colour=color
            )
        except Exception as e:
            logger.error("Failed to display text", error=str(e))

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
            logger.debug("Displaying icon", mode=mode, duration=display_time)
            # Use controller for matrix operations (handles state tracking)
            await self._controller.set_pixels(icon_pixels, mode)
            await asyncio.sleep(display_time)
        except Exception as e:
            logger.error("Failed to display icon", error=str(e))

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
        self._controller.set_mode("scrolling")
        await self.show_text(text, color=text_color, scroll_speed=scroll_speed)

    async def clear(self):
        """Clear the LED display"""
        try:
            # Use controller for matrix operations (handles state tracking)
            await self._controller.clear()
        except Exception as e:
            logger.error("Failed to clear display", error=str(e))
