"""
Hardware service - owns and manages SenseHat hardware instance.

This service provides a single point of ownership for the SenseHat,
eliminating module-level globals and providing clear lifecycle management.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sense_hat import SenseHat

logger = logging.getLogger(__name__)


@dataclass
class MatrixState:
    """Current state of the LED matrix."""

    pixels: list[list[int]]
    mode: str
    rotation: int
    web_offset: int
    available: bool


@dataclass
class SensorReadings:
    """Sensor readings from SenseHat."""

    temperature: float | None
    humidity: float | None
    pressure: float | None
    available: bool
    error: str | None = None


class HardwareService:
    """
    Service that owns and manages SenseHat hardware.

    This is the single source of truth for SenseHat access.
    All components should receive this service via dependency injection.

    Responsibilities:
    - Initialize SenseHat hardware
    - Provide sensor readings
    - Control LED matrix
    - Track display state

    Usage:
        service = HardwareService()
        await service.initialize()

        # Read sensors
        readings = await service.get_sensor_readings()

        # Control display
        await service.set_pixels(pixels)
        await service.clear_display()

        # Cleanup
        await service.shutdown()
    """

    def __init__(self) -> None:
        self._sense_hat: SenseHat | None = None
        self._available: bool = False
        self._initialized: bool = False
        self._lock = asyncio.Lock()

        # Display state tracking
        self._current_mode: str = "idle"
        self._current_rotation: int = 0
        self._web_rotation_offset: int = 90

    @property
    def is_available(self) -> bool:
        """Check if SenseHat hardware is available."""
        return self._available

    @property
    def is_initialized(self) -> bool:
        """Check if service has been initialized."""
        return self._initialized

    @property
    def sense_hat(self) -> SenseHat | None:
        """Get raw SenseHat instance (for advanced usage)."""
        return self._sense_hat

    @property
    def current_rotation(self) -> int:
        """Get current display rotation."""
        return self._current_rotation

    @property
    def web_rotation_offset(self) -> int:
        """Get web preview rotation offset."""
        return self._web_rotation_offset

    async def initialize(self) -> bool:
        """
        Initialize SenseHat hardware.

        Returns:
            True if hardware is available, False otherwise.
        """
        if self._initialized:
            logger.debug("HardwareService already initialized")
            return self._available

        async with self._lock:
            try:
                from sense_hat import SenseHat

                # Initialize in thread pool (blocking operation)
                self._sense_hat = await asyncio.to_thread(SenseHat)
                self._available = True
                self._initialized = True
                logger.info("HardwareService: SenseHat initialized successfully")
                return True

            except ImportError:
                logger.warning("HardwareService: sense_hat module not installed")
                self._available = False
                self._initialized = True
                return False

            except Exception as e:
                logger.warning(f"HardwareService: SenseHat not available: {e}")
                self._available = False
                self._initialized = True
                return False

    async def shutdown(self) -> None:
        """Clean up hardware resources."""
        async with self._lock:
            if self._sense_hat and self._available:
                try:
                    await asyncio.to_thread(self._sense_hat.clear)
                    logger.info("HardwareService: Display cleared on shutdown")
                except Exception as e:
                    logger.error(f"HardwareService: Error clearing display: {e}")

            self._sense_hat = None
            self._available = False
            self._initialized = False
            logger.info("HardwareService shut down")

    # =========================================================================
    # SENSOR METHODS
    # =========================================================================

    def _read_sensors_sync(self) -> SensorReadings:
        """Synchronous sensor reading (runs in thread pool)."""
        if not self._available or not self._sense_hat:
            return SensorReadings(
                temperature=None,
                humidity=None,
                pressure=None,
                available=False,
            )

        try:
            return SensorReadings(
                temperature=round(self._sense_hat.get_temperature(), 1),
                humidity=round(self._sense_hat.get_humidity(), 1),
                pressure=round(self._sense_hat.get_pressure(), 1),
                available=True,
            )
        except Exception as e:
            logger.error(f"HardwareService: Failed to read sensors: {e}")
            return SensorReadings(
                temperature=None,
                humidity=None,
                pressure=None,
                available=False,
                error=str(e),
            )

    async def get_sensor_readings(self) -> SensorReadings:
        """Get sensor readings (temperature, humidity, pressure)."""
        if not self._initialized:
            await self.initialize()

        return await asyncio.to_thread(self._read_sensors_sync)

    # =========================================================================
    # DISPLAY METHODS
    # =========================================================================

    async def set_rotation(self, rotation: int) -> bool:
        """
        Set display rotation.

        Args:
            rotation: Rotation in degrees (0, 90, 180, 270)

        Returns:
            True if successful, False otherwise.
        """
        if rotation not in (0, 90, 180, 270):
            logger.error(f"Invalid rotation: {rotation}")
            return False

        self._current_rotation = rotation

        if not self._available or not self._sense_hat:
            return False

        try:
            await asyncio.to_thread(self._sense_hat.set_rotation, rotation)
            logger.debug(f"HardwareService: Rotation set to {rotation}")
            return True
        except Exception as e:
            logger.error(f"HardwareService: Failed to set rotation: {e}")
            return False

    def set_web_rotation_offset(self, offset: int) -> None:
        """Set web preview rotation offset."""
        if offset in (0, 90, 180, 270):
            self._web_rotation_offset = offset

    def set_display_mode(self, mode: str) -> None:
        """Update current display mode label."""
        self._current_mode = mode

    async def set_pixels(self, pixels: list[list[int]], mode: str = "custom") -> bool:
        """
        Set LED matrix pixels.

        Args:
            pixels: 64-element list of [R, G, B] values
            mode: Display mode label

        Returns:
            True if successful, False otherwise.
        """
        self._current_mode = mode

        if not self._available or not self._sense_hat:
            return False

        try:
            await asyncio.to_thread(self._sense_hat.set_pixels, pixels)
            return True
        except Exception as e:
            logger.error(f"HardwareService: Failed to set pixels: {e}")
            return False

    async def clear_display(self) -> bool:
        """
        Clear the LED display.

        Returns:
            True if successful, False otherwise.
        """
        self._current_mode = "cleared"

        if not self._available or not self._sense_hat:
            return False

        try:
            await asyncio.to_thread(self._sense_hat.clear)
            return True
        except Exception as e:
            logger.error(f"HardwareService: Failed to clear display: {e}")
            return False

    async def show_message(
        self,
        text: str,
        scroll_speed: float = 0.1,
        text_colour: tuple[int, int, int] = (255, 255, 255),
    ) -> bool:
        """
        Show scrolling message on LED matrix.

        Args:
            text: Text to display
            scroll_speed: Scroll speed (lower = faster)
            text_colour: RGB color tuple

        Returns:
            True if successful, False otherwise.
        """
        self._current_mode = "scrolling"

        if not self._available or not self._sense_hat:
            return False

        try:
            await asyncio.to_thread(
                self._sense_hat.show_message,
                text,
                scroll_speed=scroll_speed,
                text_colour=text_colour,
            )
            return True
        except Exception as e:
            logger.error(f"HardwareService: Failed to show message: {e}")
            return False

    def _get_matrix_state_sync(self) -> MatrixState:
        """Synchronous matrix state retrieval."""
        if self._available and self._sense_hat:
            try:
                pixels = self._sense_hat.get_pixels()
                return MatrixState(
                    pixels=pixels,
                    mode=self._current_mode,
                    rotation=self._current_rotation,
                    web_offset=self._web_rotation_offset,
                    available=True,
                )
            except Exception:
                pass

        # Return empty matrix if unavailable
        return MatrixState(
            pixels=[[0, 0, 0] for _ in range(64)],
            mode=self._current_mode,
            rotation=self._current_rotation,
            web_offset=self._web_rotation_offset,
            available=False,
        )

    async def get_matrix_state(self) -> MatrixState:
        """Get current LED matrix state for web preview."""
        return await asyncio.to_thread(self._get_matrix_state_sync)

    def get_matrix_state_dict(self) -> dict[str, Any]:
        """Get matrix state as dictionary (synchronous, for compatibility)."""
        state = self._get_matrix_state_sync()
        return {
            "pixels": state.pixels,
            "mode": state.mode,
            "rotation": state.rotation,
            "web_offset": state.web_offset,
            "available": state.available,
        }
