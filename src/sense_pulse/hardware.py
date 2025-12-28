"""Hardware abstraction - graceful degradation when Sense HAT unavailable"""

import logging
from typing import Dict, List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from sense_hat import SenseHat

logger = logging.getLogger(__name__)

# Try to import Sense HAT, but don't fail if unavailable
_sense_hat: Optional["SenseHat"] = None
_sense_hat_available: bool = False
_initialized: bool = False

# Track current LED matrix state (8x8 grid of RGB values)
# Each pixel is [R, G, B] with values 0-255
_current_matrix: List[List[int]] = [[0, 0, 0] for _ in range(64)]
_current_display_mode: str = "idle"


def _init_sense_hat() -> None:
    """Lazy initialization of Sense HAT"""
    global _sense_hat, _sense_hat_available, _initialized

    if _initialized:
        return

    _initialized = True

    try:
        from sense_hat import SenseHat
        _sense_hat = SenseHat()
        _sense_hat_available = True
        logger.info("Sense HAT initialized successfully")
    except ImportError:
        logger.warning("sense_hat module not installed - sensor data unavailable")
        _sense_hat_available = False
    except Exception as e:
        logger.warning(f"Sense HAT hardware not available: {e}")
        _sense_hat_available = False


def is_sense_hat_available() -> bool:
    """Check if Sense HAT is available"""
    _init_sense_hat()
    return _sense_hat_available


def get_sense_hat() -> Optional["SenseHat"]:
    """Get Sense HAT instance or None if unavailable"""
    _init_sense_hat()
    return _sense_hat


def get_sensor_data() -> Dict[str, Any]:
    """Get sensor readings, returns None values if hardware unavailable"""
    _init_sense_hat()

    if not _sense_hat_available or _sense_hat is None:
        return {
            "temperature": None,
            "humidity": None,
            "pressure": None,
            "available": False,
        }

    try:
        return {
            "temperature": round(_sense_hat.get_temperature(), 1),
            "humidity": round(_sense_hat.get_humidity(), 1),
            "pressure": round(_sense_hat.get_pressure(), 1),
            "available": True,
        }
    except Exception as e:
        logger.error(f"Failed to read sensors: {e}")
        return {
            "temperature": None,
            "humidity": None,
            "pressure": None,
            "available": False,
            "error": str(e),
        }


def clear_display() -> Dict[str, str]:
    """Clear LED matrix if available"""
    global _current_matrix, _current_display_mode
    _init_sense_hat()

    # Always update tracked state
    _current_matrix = [[0, 0, 0] for _ in range(64)]
    _current_display_mode = "cleared"

    if not _sense_hat_available or _sense_hat is None:
        return {"status": "skipped", "message": "Sense HAT not available"}

    try:
        _sense_hat.clear()
        return {"status": "ok", "message": "Display cleared"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def set_pixels(pixels: List[List[int]], mode: str = "custom") -> Dict[str, str]:
    """Set LED matrix pixels if available"""
    global _current_matrix, _current_display_mode
    _init_sense_hat()

    # Always track state even if hardware unavailable
    _current_matrix = pixels.copy() if pixels else [[0, 0, 0] for _ in range(64)]
    _current_display_mode = mode

    if not _sense_hat_available or _sense_hat is None:
        return {"status": "skipped", "message": "Sense HAT not available"}

    try:
        _sense_hat.set_pixels(pixels)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def set_rotation(rotation: int) -> Dict[str, str]:
    """Set LED matrix rotation if available"""
    _init_sense_hat()

    if not _sense_hat_available or _sense_hat is None:
        return {"status": "skipped", "message": "Sense HAT not available"}

    try:
        _sense_hat.set_rotation(rotation)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_matrix_state() -> Dict[str, Any]:
    """Get current LED matrix state for web preview (reads directly from hardware)"""
    _init_sense_hat()

    if _sense_hat_available and _sense_hat is not None:
        try:
            # Read actual pixel state from hardware for real-time updates
            pixels = _sense_hat.get_pixels()
            return {
                "pixels": pixels,
                "mode": _current_display_mode,
                "available": True,
            }
        except Exception:
            pass

    # Fallback to tracked state if hardware unavailable
    return {
        "pixels": _current_matrix,
        "mode": _current_display_mode,
        "available": _sense_hat_available,
    }


def set_display_mode(mode: str) -> None:
    """Update the current display mode label"""
    global _current_display_mode
    _current_display_mode = mode


def update_matrix_state(pixels: List[List[int]], mode: str = "custom") -> None:
    """Update tracked matrix state without setting hardware (for external updates)"""
    global _current_matrix, _current_display_mode
    _current_matrix = pixels.copy() if pixels else [[0, 0, 0] for _ in range(64)]
    _current_display_mode = mode
