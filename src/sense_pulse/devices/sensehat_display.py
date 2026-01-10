"""LED matrix display control for SenseHat.

This module provides display control functionality for the SenseHat LED matrix.
It can work with a shared SenseHat instance (recommended) or create its own.

Usage:
    # With shared instance (recommended)
    from sense_hat import SenseHat
    sense_hat = SenseHat()
    display = SenseHatDisplayController(sense_hat)
    await display.set_pixels(pixels)

    # With lazy initialization (fallback)
    display = SenseHatDisplayController()
    if display.available:
        await display.clear()
"""

import asyncio
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from sense_hat import SenseHat

from ..web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="sensehat.display")


class SenseHatDisplayController:
    """
    Manages LED matrix output on SenseHat hardware.

    This class provides control over the SenseHat's 8x8 LED matrix display.
    It tracks display state for web preview and can use a provided SenseHat
    instance or lazily initialize its own.

    Attributes:
        available: Whether the SenseHat hardware is available for display
        rotation: Current display rotation (0, 90, 180, 270)
        current_mode: Semantic label for what's currently displayed
    """

    def __init__(self, sense_hat: Optional["SenseHat"] = None):
        """
        Initialize SenseHat display controller.

        Args:
            sense_hat: Optional SenseHat instance to use. If not provided,
                      will attempt lazy initialization when first accessed.
        """
        self._sense_hat: Optional[SenseHat] = sense_hat
        self._available: Optional[bool] = None if sense_hat is None else True
        self._initialized: bool = sense_hat is not None

        # Display state tracking
        self._rotation: int = 0
        self._current_mode: str = "idle"

        if sense_hat is not None:
            logger.debug("SenseHatDisplayController initialized with provided instance")

    def _ensure_initialized(self) -> bool:
        """Lazy initialization of SenseHat if not provided."""
        if self._initialized:
            return self._available or False

        self._initialized = True

        try:
            from sense_hat import SenseHat

            self._sense_hat = SenseHat()
            self._available = True
            logger.info("SenseHat display initialized via lazy initialization")
        except ImportError:
            logger.warning("SenseHat module not installed", available=False)
            self._available = False
        except Exception as e:
            logger.warning("SenseHat hardware not available", error=str(e))
            self._available = False

        return self._available or False

    @property
    def available(self) -> bool:
        """Check if SenseHat display is available."""
        return self._ensure_initialized()

    @property
    def sense_hat(self) -> Optional["SenseHat"]:
        """Get the underlying SenseHat instance."""
        self._ensure_initialized()
        return self._sense_hat

    @property
    def rotation(self) -> int:
        """Get current display rotation."""
        return self._rotation

    @property
    def current_mode(self) -> str:
        """Get current display mode label."""
        return self._current_mode

    def set_rotation_sync(self, rotation: int) -> dict[str, str]:
        """
        Set LED matrix rotation synchronously.

        Args:
            rotation: Rotation angle (0, 90, 180, or 270)

        Returns:
            Status dictionary with result
        """
        self._rotation = rotation

        if not self.available or self._sense_hat is None:
            return {"status": "skipped", "message": "SenseHat not available"}

        try:
            self._sense_hat.set_rotation(rotation)
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def set_rotation(self, rotation: int) -> dict[str, str]:
        """
        Set LED matrix rotation asynchronously.

        Args:
            rotation: Rotation angle (0, 90, 180, or 270)

        Returns:
            Status dictionary with result
        """
        return await asyncio.to_thread(self.set_rotation_sync, rotation)

    def set_mode(self, mode: str) -> None:
        """
        Update the current display mode label.

        Args:
            mode: Semantic label for what's being displayed (e.g., "pihole", "tailscale")
        """
        self._current_mode = mode

    def clear_sync(self) -> dict[str, str]:
        """
        Clear LED matrix synchronously.

        Returns:
            Status dictionary with result
        """
        self._current_mode = "cleared"

        if not self.available or self._sense_hat is None:
            return {"status": "skipped", "message": "SenseHat not available"}

        try:
            self._sense_hat.clear()
            return {"status": "ok", "message": "Display cleared"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def clear(self) -> dict[str, str]:
        """
        Clear LED matrix asynchronously.

        Returns:
            Status dictionary with result
        """
        return await asyncio.to_thread(self.clear_sync)

    def set_pixels_sync(self, pixels: list[list[int]], mode: str = "custom") -> dict[str, str]:
        """
        Set LED matrix pixels synchronously.

        Args:
            pixels: 64-element list of [R, G, B] values
            mode: Display mode label for tracking

        Returns:
            Status dictionary with result
        """
        self._current_mode = mode

        if not self.available or self._sense_hat is None:
            return {"status": "skipped", "message": "SenseHat not available"}

        try:
            self._sense_hat.set_pixels(pixels)
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def set_pixels(self, pixels: list[list[int]], mode: str = "custom") -> dict[str, str]:
        """
        Set LED matrix pixels asynchronously.

        Args:
            pixels: 64-element list of [R, G, B] values
            mode: Display mode label for tracking

        Returns:
            Status dictionary with result
        """
        return await asyncio.to_thread(self.set_pixels_sync, pixels, mode)

    def get_matrix_state_sync(self) -> dict[str, Any]:
        """
        Get current LED matrix state for web preview synchronously.

        Returns:
            Dictionary with pixels, mode, rotation, and availability status
        """
        if self.available and self._sense_hat is not None:
            try:
                pixels = self._sense_hat.get_pixels()
                return {
                    "pixels": pixels,
                    "mode": self._current_mode,
                    "rotation": self._rotation,
                    "available": True,
                }
            except Exception:
                pass

        # Hardware unavailable - return empty matrix
        return {
            "pixels": [[0, 0, 0] for _ in range(64)],
            "mode": self._current_mode,
            "rotation": self._rotation,
            "available": False,
        }

    async def get_matrix_state(self) -> dict[str, Any]:
        """
        Get current LED matrix state for web preview asynchronously.

        Returns:
            Dictionary with pixels, mode, rotation, and availability status
        """
        return await asyncio.to_thread(self.get_matrix_state_sync)
