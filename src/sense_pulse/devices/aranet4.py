"""Aranet4 CO2 sensor communication via aranet4 package async BLE scan"""

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from ..web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="aranet4")

# Async lock for BLE operations (prevents D-Bus connection exhaustion)
_async_scan_lock: Optional[asyncio.Lock] = None
_last_scan_time: float = 0
_scan_cooldown = 5  # Minimum seconds between scans


@dataclass
class Aranet4Reading:
    """Data class for Aranet4 sensor readings"""

    co2: int  # ppm
    temperature: float  # Celsius
    humidity: int  # %
    pressure: float  # mbar
    battery: int  # %
    interval: int  # Measurement interval in seconds
    ago: int  # Seconds since last measurement
    timestamp: float  # When this reading was cached

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "co2": self.co2,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "pressure": self.pressure,
            "battery": self.battery,
            "interval": self.interval,
            "ago": self.ago,
        }


class Aranet4Sensor:
    """Handles communication with Aranet4 CO2 sensor via Bluetooth LE"""

    def __init__(
        self,
        mac_address: str,
        name: str = "sensor",
        cache_duration: int = 60,
    ):
        self.mac_address = mac_address.upper()
        self.name = name
        self.cache_duration = cache_duration
        self._cached_reading: Optional[Aranet4Reading] = None
        self._last_error: Optional[str] = None
        self._lock = threading.Lock()

    def update_reading(self, reading: Aranet4Reading) -> None:
        """Update cached reading (called by polling loop)"""
        with self._lock:
            self._cached_reading = reading
            self._last_error = None
        logger.info(
            "Aranet4 reading updated",
            sensor=self.name,
            co2=reading.co2,
            temperature=reading.temperature,
            humidity=reading.humidity,
            battery=reading.battery,
        )

    def set_error(self, error: str) -> None:
        """Set error state (called by polling loop)"""
        with self._lock:
            self._last_error = error

    def get_cached_reading(self) -> Optional[Aranet4Reading]:
        """
        Get cached reading only. Does NOT trigger BLE connection.
        Use this from web server and display code.
        """
        with self._lock:
            return self._cached_reading

    def get_co2(self) -> Optional[int]:
        """Get cached CO2 level in ppm"""
        reading = self.get_cached_reading()
        return reading.co2 if reading else None

    def get_status(self) -> dict[str, Any]:
        """Get sensor status including last reading and any errors"""
        with self._lock:
            reading = self._cached_reading
            return {
                "name": self.name,
                "mac_address": self.mac_address,
                "connected": reading is not None
                and (time.time() - reading.timestamp) < self.cache_duration,
                "last_reading": reading.to_dict() if reading else None,
                "cache_age": int(time.time() - reading.timestamp) if reading else None,
                "last_error": self._last_error,
            }


# ============================================================================
# Async BLE Scanning (prevents D-Bus connection exhaustion)
# ============================================================================


def _get_async_scan_lock() -> asyncio.Lock:
    """Get or create the async scan lock (must be called from async context)"""
    global _async_scan_lock
    if _async_scan_lock is None:
        _async_scan_lock = asyncio.Lock()
    return _async_scan_lock


async def do_ble_scan_async(scan_duration: int = 8) -> dict[str, Aranet4Reading]:
    """Run async BLE scan using aranet4's internal async API.

    This avoids the D-Bus connection exhaustion issue caused by repeated
    asyncio.run() calls in the synchronous find_nearby() function.

    Uses aranet4.client._find_nearby() directly within the existing event loop
    instead of find_nearby() which creates a new event loop each time.

    Args:
        scan_duration: Duration of BLE scan in seconds

    Returns:
        Dictionary mapping MAC addresses to Aranet4Reading objects
    """
    global _last_scan_time

    try:
        # Import aranet4's internal async function
        from aranet4.client import _find_nearby

        # Acquire async lock to prevent concurrent scans
        async with _get_async_scan_lock():
            # Enforce cooldown period between scans
            time_since_last_scan = time.time() - _last_scan_time
            if time_since_last_scan < _scan_cooldown:
                wait_time = _scan_cooldown - time_since_last_scan
                logger.debug("Aranet4 async scan cooldown", wait_seconds=round(wait_time, 1))
                await asyncio.sleep(wait_time)

            logger.info("Aranet4 running async BLE scan", duration=scan_duration)
            _last_scan_time = time.time()
            readings: dict[str, Aranet4Reading] = {}

            def on_detect(advertisement):
                if advertisement.readings:
                    address = advertisement.device.address.upper()
                    readings[address] = Aranet4Reading(
                        co2=advertisement.readings.co2,
                        temperature=round(advertisement.readings.temperature, 1),
                        humidity=advertisement.readings.humidity,
                        pressure=round(advertisement.readings.pressure, 1),
                        battery=advertisement.readings.battery,
                        interval=advertisement.readings.interval,
                        ago=advertisement.readings.ago,
                        timestamp=time.time(),
                    )
                    logger.debug(
                        "Aranet4 device found",
                        address=address,
                        co2=advertisement.readings.co2,
                    )

            # Use the async _find_nearby directly instead of sync find_nearby
            # This prevents creating new event loops and accumulating D-Bus connections
            await _find_nearby(on_detect, scan_duration)

            logger.info("Aranet4 async scan completed", devices_found=len(readings))
            return readings

    except ImportError:
        logger.error("Aranet4 package not installed")
        return {}
    except Exception as e:
        logger.warning("Aranet4 async scan error", error=str(e))
        raise


async def scan_for_aranet4_async(duration: int = 10) -> list[dict[str, Any]]:
    """Async scan for Aranet4 devices in range.

    Uses aranet4's internal async API to avoid D-Bus connection exhaustion.

    Args:
        duration: Duration of scan in seconds

    Returns:
        List of discovered devices with their info
    """
    global _last_scan_time

    try:
        from aranet4.client import Aranet4Scanner

        async with _get_async_scan_lock():
            # Enforce cooldown period between scans
            time_since_last_scan = time.time() - _last_scan_time
            if time_since_last_scan < _scan_cooldown:
                wait_time = _scan_cooldown - time_since_last_scan
                logger.debug(
                    "Aranet4 async discovery scan cooldown", wait_seconds=round(wait_time, 1)
                )
                await asyncio.sleep(wait_time)

            logger.info("Scanning for Aranet4 devices", duration=duration)
            _last_scan_time = time.time()

            found_devices: list[dict[str, Any]] = []
            seen_addresses: set = set()

            def on_detect(advertisement):
                if advertisement.device.address not in seen_addresses:
                    seen_addresses.add(advertisement.device.address)
                    device_info: dict[str, Any] = {
                        "name": advertisement.device.name or "Aranet4",
                        "address": advertisement.device.address.upper(),
                        "rssi": advertisement.rssi,
                    }
                    if advertisement.readings:
                        device_info["co2"] = advertisement.readings.co2
                        device_info["temperature"] = advertisement.readings.temperature
                        device_info["humidity"] = advertisement.readings.humidity
                    found_devices.append(device_info)
                    logger.info(
                        "Aranet4 device found",
                        name=device_info["name"],
                        address=device_info["address"],
                    )

            # Use Aranet4Scanner directly for proper lifecycle management
            scanner = Aranet4Scanner(on_detect)
            await scanner.start()
            await asyncio.sleep(duration)
            await scanner.stop()

            logger.info("Aranet4 scan complete", devices_found=len(found_devices))
            return found_devices

    except ImportError:
        logger.error("Aranet4 library not installed - cannot scan")
        return []
    except Exception as e:
        logger.error("Async BLE scan error", error=str(e))
        return []
