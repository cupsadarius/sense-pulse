"""Hardware abstraction - graceful degradation when Sense HAT unavailable"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from sense_hat import SenseHat

    from sense_pulse.aranet4 import Aranet4Sensor

logger = logging.getLogger(__name__)

# Try to import Sense HAT, but don't fail if unavailable
_sense_hat: Optional["SenseHat"] = None
_sense_hat_available: bool = False
_initialized: bool = False

# Track current display mode (semantic label for what's being shown)
_current_display_mode: str = "idle"
_current_rotation: int = 0
_web_rotation_offset: int = 90  # Default offset for web preview

# Aranet4 CO2 sensors (dynamic list by label)
_aranet4_sensors: dict[str, "Aranet4Sensor"] = {}  # label -> Aranet4Sensor
_aranet4_initialized: bool = False


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


def _get_sensor_data_sync() -> dict[str, Any]:
    """Synchronous version - get sensor readings, returns None values if hardware unavailable"""
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


async def get_sensor_data() -> dict[str, Any]:
    """Get sensor readings (async wrapper), returns None values if hardware unavailable"""
    return await asyncio.to_thread(_get_sensor_data_sync)


def _clear_display_sync() -> dict[str, str]:
    """Synchronous version - clear LED matrix if available"""
    global _current_display_mode
    _init_sense_hat()

    _current_display_mode = "cleared"

    if not _sense_hat_available or _sense_hat is None:
        return {"status": "skipped", "message": "Sense HAT not available"}

    try:
        _sense_hat.clear()
        return {"status": "ok", "message": "Display cleared"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def clear_display() -> dict[str, str]:
    """Clear LED matrix if available (async wrapper)"""
    return await asyncio.to_thread(_clear_display_sync)


def _set_pixels_sync(pixels: list[list[int]], mode: str = "custom") -> dict[str, str]:
    """Synchronous version - set LED matrix pixels if available"""
    global _current_display_mode
    _init_sense_hat()

    _current_display_mode = mode

    if not _sense_hat_available or _sense_hat is None:
        return {"status": "skipped", "message": "Sense HAT not available"}

    try:
        _sense_hat.set_pixels(pixels)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def set_pixels(pixels: list[list[int]], mode: str = "custom") -> dict[str, str]:
    """Set LED matrix pixels if available (async wrapper)"""
    return await asyncio.to_thread(_set_pixels_sync, pixels, mode)


def _set_rotation_sync(rotation: int) -> dict[str, str]:
    """Synchronous version - set LED matrix rotation if available"""
    global _current_rotation
    _init_sense_hat()

    _current_rotation = rotation

    if not _sense_hat_available or _sense_hat is None:
        return {"status": "skipped", "message": "Sense HAT not available"}

    try:
        _sense_hat.set_rotation(rotation)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def set_rotation(rotation: int) -> dict[str, str]:
    """Set LED matrix rotation if available (async wrapper)"""
    return await asyncio.to_thread(_set_rotation_sync, rotation)


def _get_matrix_state_sync() -> dict[str, Any]:
    """Synchronous version - get current LED matrix state for web preview"""
    _init_sense_hat()

    if _sense_hat_available and _sense_hat is not None:
        try:
            # Read actual pixel state from hardware for real-time updates
            pixels = _sense_hat.get_pixels()
            return {
                "pixels": pixels,
                "mode": _current_display_mode,
                "rotation": _current_rotation,
                "web_offset": _web_rotation_offset,
                "available": True,
            }
        except Exception:
            pass

    # Hardware unavailable - return empty matrix
    return {
        "pixels": [[0, 0, 0] for _ in range(64)],
        "mode": _current_display_mode,
        "rotation": _current_rotation,
        "web_offset": _web_rotation_offset,
        "available": False,
    }


async def get_matrix_state() -> dict[str, Any]:
    """Get current LED matrix state for web preview (async wrapper)"""
    return await asyncio.to_thread(_get_matrix_state_sync)


def set_web_rotation_offset(offset: int) -> None:
    """Set web preview rotation offset"""
    global _web_rotation_offset
    _web_rotation_offset = offset


def set_display_mode(mode: str) -> None:
    """Update the current display mode label"""
    global _current_display_mode
    _current_display_mode = mode


def init_aranet4_sensors(
    sensors: list[dict[str, Any]] = None,
    timeout: int = 30,
    cache_duration: int = 60,
) -> None:
    """Initialize Aranet4 CO2 sensors and start background polling

    Args:
        sensors: List of sensor configs, each with 'label', 'mac_address', and 'enabled' fields
        timeout: Connection timeout in seconds
        cache_duration: Cache duration in seconds
    """
    global _aranet4_sensors, _aranet4_initialized

    if _aranet4_initialized:
        return

    _aranet4_initialized = True

    if sensors is None:
        sensors = []

    try:
        from sense_pulse.aranet4 import Aranet4Sensor, register_sensor

        for sensor_config in sensors:
            label = sensor_config.get("label", "")
            mac_address = sensor_config.get("mac_address", "")
            enabled = sensor_config.get("enabled", False)

            if enabled and mac_address and label:
                sensor = Aranet4Sensor(
                    mac_address=mac_address,
                    name=label,
                    cache_duration=cache_duration,
                )
                _aranet4_sensors[label] = sensor
                register_sensor(sensor)
                logger.info(f"Aranet4 sensor '{label}' configured: {mac_address}")

    except ImportError:
        logger.warning("Aranet4 module not available - CO2 sensors disabled")
    except Exception as e:
        logger.error(f"Failed to initialize Aranet4 sensors: {e}")


def update_aranet4_sensors(
    sensors: list[dict[str, Any]],
    timeout: int = 30,
    cache_duration: int = 60,
) -> dict[str, str]:
    """Update all Aranet4 sensor configurations

    Args:
        sensors: List of sensor configs, each with 'label', 'mac_address', and 'enabled' fields
        timeout: Connection timeout in seconds
        cache_duration: Cache duration in seconds
    """
    global _aranet4_sensors

    try:
        from sense_pulse.aranet4 import Aranet4Sensor, register_sensor, unregister_sensor

        # Unregister all existing sensors
        for _label, sensor in list(_aranet4_sensors.items()):
            unregister_sensor(sensor)
        _aranet4_sensors.clear()

        # Register new sensors
        for sensor_config in sensors:
            label = sensor_config.get("label", "")
            mac_address = sensor_config.get("mac_address", "")
            enabled = sensor_config.get("enabled", False)

            if enabled and mac_address and label:
                sensor = Aranet4Sensor(
                    mac_address=mac_address,
                    name=label,
                    cache_duration=cache_duration,
                )
                _aranet4_sensors[label] = sensor
                register_sensor(sensor)
                logger.info(f"Aranet4 sensor '{label}' updated: {mac_address}")

        return {"status": "ok", "message": f"Updated {len(_aranet4_sensors)} sensor(s)"}

    except ImportError:
        return {"status": "error", "message": "Aranet4 module not available"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_aranet4_data() -> dict[str, Any]:
    """Get CO2 sensor data from cache only (does not trigger BLE)"""
    result = {}

    for label, sensor in _aranet4_sensors.items():
        reading = sensor.get_cached_reading()
        if reading:
            result[label] = reading.to_dict()

    return result if result else {"available": False}


def get_aranet4_status() -> dict[str, Any]:
    """Get status of all Aranet4 sensors"""
    result = {}

    for label, sensor in _aranet4_sensors.items():
        result[label] = sensor.get_status()

    return result


def is_aranet4_available() -> bool:
    """Check if any Aranet4 sensor is configured"""
    return len(_aranet4_sensors) > 0
