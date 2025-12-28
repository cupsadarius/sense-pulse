"""Hardware abstraction - graceful degradation when Sense HAT unavailable"""

import logging
from typing import Dict, List, Optional, Any, TYPE_CHECKING

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

# Aranet4 CO2 sensors
_aranet4_office: Optional["Aranet4Sensor"] = None
_aranet4_bedroom: Optional["Aranet4Sensor"] = None
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


def set_pixels(pixels: List[List[int]], mode: str = "custom") -> Dict[str, str]:
    """Set LED matrix pixels if available"""
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


def set_rotation(rotation: int) -> Dict[str, str]:
    """Set LED matrix rotation if available"""
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


def set_web_rotation_offset(offset: int) -> None:
    """Set web preview rotation offset"""
    global _web_rotation_offset
    _web_rotation_offset = offset


def set_display_mode(mode: str) -> None:
    """Update the current display mode label"""
    global _current_display_mode
    _current_display_mode = mode


def init_aranet4_sensors(
    office_mac: str = "",
    bedroom_mac: str = "",
    office_enabled: bool = False,
    bedroom_enabled: bool = False,
    timeout: int = 10,
    cache_duration: int = 60,
) -> None:
    """Initialize Aranet4 CO2 sensors"""
    global _aranet4_office, _aranet4_bedroom, _aranet4_initialized

    if _aranet4_initialized:
        return

    _aranet4_initialized = True

    try:
        from sense_pulse.aranet4 import Aranet4Sensor

        if office_enabled and office_mac:
            _aranet4_office = Aranet4Sensor(
                mac_address=office_mac,
                name="office",
                timeout=timeout,
                cache_duration=cache_duration,
            )
            logger.info(f"Aranet4 office sensor configured: {office_mac}")

        if bedroom_enabled and bedroom_mac:
            _aranet4_bedroom = Aranet4Sensor(
                mac_address=bedroom_mac,
                name="bedroom",
                timeout=timeout,
                cache_duration=cache_duration,
            )
            logger.info(f"Aranet4 bedroom sensor configured: {bedroom_mac}")

    except ImportError:
        logger.warning("Aranet4 module not available - CO2 sensors disabled")
    except Exception as e:
        logger.error(f"Failed to initialize Aranet4 sensors: {e}")


def update_aranet4_sensor(
    sensor_name: str,
    mac_address: str,
    enabled: bool,
    timeout: int = 10,
    cache_duration: int = 60,
) -> Dict[str, str]:
    """Update a single Aranet4 sensor configuration"""
    global _aranet4_office, _aranet4_bedroom

    try:
        from sense_pulse.aranet4 import Aranet4Sensor

        if sensor_name == "office":
            if enabled and mac_address:
                _aranet4_office = Aranet4Sensor(
                    mac_address=mac_address,
                    name="office",
                    timeout=timeout,
                    cache_duration=cache_duration,
                )
                logger.info(f"Aranet4 office sensor updated: {mac_address}")
            else:
                _aranet4_office = None
                logger.info("Aranet4 office sensor disabled")
            return {"status": "ok", "message": f"Office sensor {'enabled' if enabled else 'disabled'}"}

        elif sensor_name == "bedroom":
            if enabled and mac_address:
                _aranet4_bedroom = Aranet4Sensor(
                    mac_address=mac_address,
                    name="bedroom",
                    timeout=timeout,
                    cache_duration=cache_duration,
                )
                logger.info(f"Aranet4 bedroom sensor updated: {mac_address}")
            else:
                _aranet4_bedroom = None
                logger.info("Aranet4 bedroom sensor disabled")
            return {"status": "ok", "message": f"Bedroom sensor {'enabled' if enabled else 'disabled'}"}

        else:
            return {"status": "error", "message": f"Unknown sensor: {sensor_name}"}

    except ImportError:
        return {"status": "error", "message": "Aranet4 module not available"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_aranet4_data() -> Dict[str, Any]:
    """Get CO2 sensor data from Aranet4 devices"""
    result = {
        "office": None,
        "bedroom": None,
        "available": False,
    }

    if _aranet4_office is not None:
        try:
            reading = _aranet4_office.get_reading()
            if reading:
                result["office"] = reading.to_dict()
                result["available"] = True
        except Exception as e:
            logger.error(f"Failed to read office sensor: {e}")

    if _aranet4_bedroom is not None:
        try:
            reading = _aranet4_bedroom.get_reading()
            if reading:
                result["bedroom"] = reading.to_dict()
                result["available"] = True
        except Exception as e:
            logger.error(f"Failed to read bedroom sensor: {e}")

    return result


def get_aranet4_status() -> Dict[str, Any]:
    """Get status of Aranet4 sensors"""
    return {
        "office": _aranet4_office.get_status() if _aranet4_office else None,
        "bedroom": _aranet4_bedroom.get_status() if _aranet4_bedroom else None,
        "office_configured": _aranet4_office is not None,
        "bedroom_configured": _aranet4_bedroom is not None,
    }


def is_aranet4_available() -> bool:
    """Check if any Aranet4 sensor is configured"""
    return _aranet4_office is not None or _aranet4_bedroom is not None
