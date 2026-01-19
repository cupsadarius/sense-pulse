"""Control Raspberry Pi onboard LEDs (PWR and ACT)"""

from pathlib import Path
from typing import Any

from .web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="pi_leds")

# Raspberry Pi LED paths - try multiple locations for compatibility
LED_PATHS = {
    "pwr": [
        Path("/sys/class/leds/PWR"),
        Path("/sys/class/leds/led1"),
    ],
    "act": [
        Path("/sys/class/leds/ACT"),
        Path("/sys/class/leds/led0"),
    ],
}

# Store original trigger values to restore later
_original_triggers: dict[str, str] = {}


def _find_led_path(led_name: str) -> Path | None:
    """Find the correct path for a given LED"""
    for path in LED_PATHS.get(led_name, []):
        if path.exists():
            return path
    return None


def _read_file(path: Path) -> str | None:
    """Safely read a file"""
    try:
        return path.read_text().strip()
    except (PermissionError, OSError) as e:
        logger.debug("Cannot read file", path=str(path), error=str(e))
        return None


def _write_file(path: Path, value: str) -> bool:
    """Safely write to a file"""
    try:
        path.write_text(value)
        return True
    except (PermissionError, OSError) as e:
        logger.warning("Cannot write to file", path=str(path), error=str(e))
        return False


def _get_current_trigger(led_path: Path) -> str | None:
    """Get the current trigger for an LED (the one in brackets)"""
    trigger_path = led_path / "trigger"
    content = _read_file(trigger_path)
    if content is None:
        return None

    # Trigger file format: "none mmc0 [heartbeat] default-on"
    # The active trigger is in brackets
    for part in content.split():
        if part.startswith("[") and part.endswith("]"):
            return part[1:-1]
    return None


def is_pi_led_available() -> bool:
    """Check if Pi onboard LEDs are controllable"""
    pwr_path = _find_led_path("pwr")
    act_path = _find_led_path("act")
    return pwr_path is not None or act_path is not None


def disable_led(led_name: str) -> dict[str, str]:
    """
    Disable a Pi onboard LED by setting brightness to 0.

    Args:
        led_name: Either "pwr" (red) or "act" (green/yellow)

    Returns:
        Status dict with result
    """
    led_path = _find_led_path(led_name)
    if led_path is None:
        return {"status": "skipped", "message": f"LED {led_name} not found"}

    # Save original trigger if not already saved
    if led_name not in _original_triggers:
        trigger = _get_current_trigger(led_path)
        if trigger:
            _original_triggers[led_name] = trigger
            logger.debug("Saved original trigger", led=led_name, trigger=trigger)

    # Set trigger to none to allow manual control
    trigger_path = led_path / "trigger"
    if not _write_file(trigger_path, "none"):
        return {"status": "error", "message": f"Cannot set trigger for {led_name}"}

    # Set brightness to 0 (off)
    brightness_path = led_path / "brightness"
    if _write_file(brightness_path, "0"):
        logger.info("Disabled LED", led=led_name.upper())
        return {"status": "ok", "message": f"{led_name} LED disabled"}
    else:
        return {"status": "error", "message": f"Cannot set brightness for {led_name}"}


def enable_led(led_name: str) -> dict[str, str]:
    """
    Re-enable a Pi onboard LED by restoring its original trigger.

    Args:
        led_name: Either "pwr" (red) or "act" (green/yellow)

    Returns:
        Status dict with result
    """
    led_path = _find_led_path(led_name)
    if led_path is None:
        return {"status": "skipped", "message": f"LED {led_name} not found"}

    trigger_path = led_path / "trigger"

    # Restore original trigger or use sensible defaults
    original = _original_triggers.get(led_name)
    if original:
        if _write_file(trigger_path, original):
            logger.info("Restored LED trigger", led=led_name.upper(), trigger=original)
            return {"status": "ok", "message": f"{led_name} LED restored to {original}"}
    else:
        # Use default triggers if we don't have original
        default_triggers = {
            "pwr": "default-on",
            "act": "mmc0",  # Activity LED typically shows SD card activity
        }
        default = default_triggers.get(led_name, "default-on")
        if _write_file(trigger_path, default):
            logger.info("Enabled LED with default trigger", led=led_name.upper(), trigger=default)
            return {"status": "ok", "message": f"{led_name} LED enabled with {default}"}

    return {"status": "error", "message": f"Cannot restore trigger for {led_name}"}


def disable_all_leds() -> dict[str, dict[str, str]]:
    """Disable both PWR and ACT LEDs"""
    return {
        "pwr": disable_led("pwr"),
        "act": disable_led("act"),
    }


def enable_all_leds() -> dict[str, dict[str, str]]:
    """Re-enable both PWR and ACT LEDs"""
    return {
        "pwr": enable_led("pwr"),
        "act": enable_led("act"),
    }


def get_led_status() -> dict[str, dict[str, Any]]:
    """Get current status of Pi onboard LEDs"""
    status: dict[str, dict[str, Any]] = {}
    for led_name in ["pwr", "act"]:
        led_path = _find_led_path(led_name)
        if led_path is None:
            status[led_name] = {"available": False}
            continue

        brightness_path = led_path / "brightness"
        trigger = _get_current_trigger(led_path)
        brightness = _read_file(brightness_path)

        status[led_name] = {
            "available": True,
            "path": str(led_path),
            "trigger": trigger,
            "brightness": brightness,
            "original_trigger": _original_triggers.get(led_name),
        }

    return status
