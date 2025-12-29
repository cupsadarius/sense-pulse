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


# Background polling thread
_polling_thread: Optional[threading.Thread] = None
_polling_stop_event = threading.Event()
_sensors_to_poll: list[Aranet4Sensor] = []
_poll_interval = 30  # seconds
_scan_duration = 8  # seconds for BLE scan


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(2),  # Only 1 retry for BLE to avoid long delays
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _do_scan() -> dict[str, Aranet4Reading]:
    """Run aranet4 package scan and return readings by MAC address (with retries)"""
    try:
        import aranet4

        logger.info("Aranet4: Running BLE scan...")
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

        aranet4.client.find_nearby(on_detect, duration=_scan_duration)
        logger.info(f"Aranet4: Scan found {len(readings)} device(s)")
        return readings

    except ImportError:
        logger.error("Aranet4: aranet4 package not installed")
        return {}
    except Exception as e:
        logger.warning(f"Aranet4: Scan error (may retry): {e}")
        raise


def _polling_loop():
    """Background thread that scans for all sensors at once"""
    logger.info("Aranet4 background polling started")

    while not _polling_stop_event.is_set():
        try:
            # Single scan gets all devices
            readings = _do_scan()

            # Update each registered sensor with its reading
            for sensor in _sensors_to_poll:
                if sensor.mac_address in readings:
                    sensor.update_reading(readings[sensor.mac_address])
                else:
                    sensor.set_error("Not found in scan")

        except Exception as e:
            logger.error(f"Aranet4 polling error: {e}")

        # Wait for next poll interval
        _polling_stop_event.wait(_poll_interval)

    logger.info("Aranet4 background polling stopped")


def register_sensor(sensor: Aranet4Sensor) -> None:
    """Register a sensor for background polling"""
    global _polling_thread

    if sensor not in _sensors_to_poll:
        _sensors_to_poll.append(sensor)
        logger.info(f"Registered Aranet4 sensor: {sensor.name} ({sensor.mac_address})")

    # Start polling thread if not running
    if _polling_thread is None or not _polling_thread.is_alive():
        _polling_stop_event.clear()
        _polling_thread = threading.Thread(target=_polling_loop, daemon=True)
        _polling_thread.start()


def unregister_sensor(sensor: Aranet4Sensor) -> None:
    """Unregister a sensor from background polling"""
    if sensor in _sensors_to_poll:
        _sensors_to_poll.remove(sensor)
        logger.info(f"Unregistered Aranet4 sensor: {sensor.name}")


def stop_polling() -> None:
    """Stop the background polling thread"""
    global _polling_thread
    _polling_stop_event.set()
    if _polling_thread and _polling_thread.is_alive():
        _polling_thread.join(timeout=5)
    _polling_thread = None


def scan_for_aranet4_devices(duration: int = 10) -> list[dict[str, Any]]:
    """Scan for Aranet4 devices in range using aranet4 package."""
    try:
        import aranet4

        logger.info(f"Scanning for Aranet4 devices ({duration}s)...")

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
    """Synchronous scan for Aranet4 devices"""
    return scan_for_aranet4_devices(duration)
