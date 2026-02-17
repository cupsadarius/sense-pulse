"""LED matrix display rendering for Sense HAT."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from sensehat.icons import get_icon

if TYPE_CHECKING:
    from sense_hat import SenseHat

logger = logging.getLogger(__name__)


class SenseHatDisplay:
    """Handles Sense HAT LED matrix display."""

    def __init__(
        self,
        sense_hat_instance: SenseHat | None = None,
        rotation: int = 0,
        scroll_speed: float = 0.08,
        icon_duration: float = 1.5,
    ):
        self.sense: SenseHat | None = sense_hat_instance
        self.rotation = rotation
        self.scroll_speed = scroll_speed
        self.icon_duration = icon_duration
        self._current_mode = "idle"

        if self.sense is not None:
            try:
                self.sense.set_rotation(rotation)
                self.sense.low_light = True
            except Exception as e:
                logger.error("Failed to configure Sense HAT display: %s", e)

    async def show_text(
        self,
        text: str,
        color: tuple[int, int, int] = (255, 255, 255),
        scroll_speed: float | None = None,
    ) -> None:
        """Display scrolling text on LED matrix."""
        if self.sense is None:
            return
        try:
            speed = scroll_speed if scroll_speed is not None else self.scroll_speed
            self._current_mode = "scrolling"
            await asyncio.to_thread(
                self.sense.show_message, text, scroll_speed=speed, text_colour=color
            )
        except Exception as e:
            logger.error("Failed to display text: %s", e)

    async def show_icon(
        self,
        icon_pixels: list[list[int]],
        duration: float | None = None,
        mode: str = "icon",
    ) -> None:
        """Display an 8x8 icon on the LED matrix."""
        if self.sense is None:
            return
        try:
            display_time = duration if duration is not None else self.icon_duration
            self._current_mode = mode
            await asyncio.to_thread(self.sense.set_pixels, icon_pixels)
            await asyncio.sleep(display_time)
        except Exception as e:
            logger.error("Failed to display icon: %s", e)

    async def show_icon_with_text(
        self,
        icon_name: str,
        text: str,
        text_color: tuple[int, int, int] = (255, 255, 255),
        icon_duration: float | None = None,
        scroll_speed: float | None = None,
    ) -> None:
        """Display an icon followed by scrolling text."""
        icon = get_icon(icon_name)
        if icon:
            await self.show_icon(icon, duration=icon_duration, mode=icon_name)
        self._current_mode = "scrolling"
        await self.show_text(text, color=text_color, scroll_speed=scroll_speed)

    async def clear(self) -> None:
        """Clear the LED display."""
        if self.sense is None:
            return
        try:
            self._current_mode = "cleared"
            await asyncio.to_thread(self.sense.clear)
        except Exception as e:
            logger.error("Failed to clear display: %s", e)

    def set_rotation(self, rotation: int) -> None:
        """Update display rotation."""
        self.rotation = rotation
        if self.sense is not None:
            try:
                self.sense.set_rotation(rotation)
            except Exception as e:
                logger.error("Failed to set rotation: %s", e)

    def get_pixels(self) -> list[list[int]]:
        """Get current pixel state from hardware."""
        if self.sense is None:
            return [[0, 0, 0]] * 64
        try:
            return self.sense.get_pixels()
        except Exception:
            return [[0, 0, 0]] * 64

    @property
    def current_mode(self) -> str:
        return self._current_mode
