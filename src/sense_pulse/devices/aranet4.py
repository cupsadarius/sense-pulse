"""Aranet4 CO2 sensor communication via aranet4 package scan"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


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
            f"Aranet4 {self.name}: CO2={reading.co2}ppm, "
            f"T={reading.temperature}°C, H={reading.humidity}%, "
            f"Battery={reading.battery}%"
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
# BLE Scanning Utilities
# ============================================================================

# Global scan lock prevents concurrent BLE operations (shared across all instances)
_scan_lock = threading.Lock()
_last_scan_time: float = 0
_scan_cooldown = 5  # Minimum seconds between scans


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(2),  # Only 1 retry for BLE to avoid long delays
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def do_ble_scan(scan_duration: int = 8) -> dict[str, Aranet4Reading]:
    """Run aranet4 package scan and return readings by MAC address (with retries)

    IMPORTANT: Must be called with _scan_lock held to prevent concurrent scans.

    Args:
        scan_duration: Duration of BLE scan in seconds

    Returns:
        Dictionary mapping MAC addresses to Aranet4Reading objects
    """
    global _last_scan_time

    try:
        import aranet4

        # Enforce cooldown period between scans
        time_since_last_scan = time.time() - _last_scan_time
        if time_since_last_scan < _scan_cooldown:
            wait_time = _scan_cooldown - time_since_last_scan
            logger.debug(f"Aranet4: Scan cooldown, waiting {wait_time:.1f}s")
            time.sleep(wait_time)

        logger.info("Aranet4: Running BLE scan...")
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
                logger.debug(f"Aranet4: Found {address} CO2={advertisement.readings.co2}")

        aranet4.client.find_nearby(on_detect, duration=scan_duration)
        logger.info(f"Aranet4: Scan found {len(readings)} device(s)")
        return readings

    except ImportError:
        logger.error("Aranet4: aranet4 package not installed")
        return {}
    except Exception as e:
        logger.warning(f"Aranet4: Scan error (may retry): {e}")
        raise


def get_scan_lock() -> threading.Lock:
    """Get the global BLE scan lock for coordinating scans across instances"""
    return _scan_lock


def scan_for_aranet4_devices(duration: int = 10) -> list[dict[str, Any]]:
    """Scan for Aranet4 devices in range using aranet4 package.

    Uses global scan lock to prevent concurrent BLE operations.

    Args:
        duration: Duration of scan in seconds

    Returns:
        List of discovered devices with their info
    """
    global _last_scan_time

    try:
        import aranet4

        # Acquire global lock to prevent concurrent scans
        with _scan_lock:
            # Enforce cooldown period between scans
            time_since_last_scan = time.time() - _last_scan_time
            if time_since_last_scan < _scan_cooldown:
                wait_time = _scan_cooldown - time_since_last_scan
                logger.debug(f"Aranet4 discovery: Scan cooldown, waiting {wait_time:.1f}s")
                time.sleep(wait_time)

            logger.info(f"Scanning for Aranet4 devices ({duration}s)...")
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
                    logger.info(f"Found: {device_info['name']} ({device_info['address']})")

            aranet4.client.find_nearby(on_detect, duration=duration)

            logger.info(f"Scan complete: found {len(found_devices)} Aranet4 device(s)")
            return found_devices

    except ImportError:
        logger.error("aranet4 library not installed - cannot scan")
        return []
    except Exception as e:
        logger.error(f"BLE scan error: {e}")
        return []


def scan_for_aranet4_sync(duration: int = 10) -> list[dict[str, Any]]:
    """Synchronous scan for Aranet4 devices (alias for scan_for_aranet4_devices)"""
    return scan_for_aranet4_devices(duration)
