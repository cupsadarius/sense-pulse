"""Aranet4 CO2 sensor communication via the aranet4 Python package"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

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

    def to_dict(self) -> Dict[str, Any]:
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
        timeout: int = 30,
        cache_duration: int = 60,
    ):
        self.mac_address = mac_address.upper()
        self.name = name
        self.timeout = timeout
        self.cache_duration = cache_duration
        self._cached_reading: Optional[Aranet4Reading] = None
        self._last_error: Optional[str] = None
        self._lock = threading.Lock()

    def poll(self) -> Optional[Aranet4Reading]:
        """
        Poll the sensor for a new reading. Called by background thread only.
        This actually connects to the BLE device.
        """
        import aranet4

        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    # Wait before retry with exponential backoff
                    wait_time = 2 ** attempt
                    logger.info(f"Aranet4 {self.name}: Retry {attempt}/{max_retries} in {wait_time}s")
                    time.sleep(wait_time)

                logger.info(f"Aranet4 {self.name}: Polling {self.mac_address}")

                # aranet4 package handles its own asyncio event loop internally
                reading = aranet4.client.get_current_readings(self.mac_address)

                if reading is None:
                    logger.warning(f"Aranet4 {self.name}: No reading returned")
                    last_error = "No reading returned"
                    continue

                result = Aranet4Reading(
                    co2=reading.co2,
                    temperature=round(reading.temperature, 1),
                    humidity=reading.humidity,
                    pressure=round(reading.pressure, 1),
                    battery=reading.battery,
                    interval=reading.interval,
                    ago=reading.ago,
                    timestamp=time.time(),
                )

                logger.info(
                    f"Aranet4 {self.name}: CO2={result.co2}ppm, "
                    f"T={result.temperature}°C, H={result.humidity}%, "
                    f"Battery={result.battery}%"
                )

                with self._lock:
                    self._cached_reading = result
                    self._last_error = None

                return result

            except Exception as e:
                last_error = str(e) if str(e) else f"{type(e).__name__}"
                logger.warning(f"Aranet4 {self.name}: Attempt {attempt+1} failed: {last_error}")

        # All retries exhausted
        logger.error(f"Aranet4 {self.name}: Poll failed after {max_retries} attempts: {last_error}")
        self._last_error = last_error
        return None

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

    def get_status(self) -> Dict[str, Any]:
        """Get sensor status including last reading and any errors"""
        with self._lock:
            reading = self._cached_reading
            return {
                "name": self.name,
                "mac_address": self.mac_address,
                "connected": reading is not None and (time.time() - reading.timestamp) < self.cache_duration,
                "last_reading": reading.to_dict() if reading else None,
                "cache_age": int(time.time() - reading.timestamp) if reading else None,
                "last_error": self._last_error,
            }


# Background polling thread
_polling_thread: Optional[threading.Thread] = None
_polling_stop_event = threading.Event()
_sensors_to_poll: List[Aranet4Sensor] = []
_poll_interval = 30  # seconds


def _polling_loop():
    """Background thread that polls all registered sensors"""
    logger.info("Aranet4 background polling started")

    while not _polling_stop_event.is_set():
        for sensor in _sensors_to_poll:
            if _polling_stop_event.is_set():
                break
            try:
                sensor.poll()
            except Exception as e:
                logger.error(f"Aranet4 polling error for {sensor.name}: {e}")

            # Longer delay between sensors to avoid BLE adapter conflicts
            if not _polling_stop_event.is_set():
                time.sleep(5)

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


def scan_for_aranet4_devices(duration: int = 10) -> List[Dict[str, Any]]:
    """Scan for Aranet4 devices in range using aranet4 package."""
    try:
        import aranet4

        logger.info(f"Scanning for Aranet4 devices ({duration}s)...")

        found_devices = []
        seen_addresses = set()

        def on_detect(advertisement):
            if advertisement.device.address not in seen_addresses:
                seen_addresses.add(advertisement.device.address)
                device_info = {
                    "name": advertisement.device.name or "Aranet4",
                    "address": advertisement.device.address,
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


def scan_for_aranet4_sync(duration: int = 10) -> List[Dict[str, Any]]:
    """Synchronous scan for Aranet4 devices"""
    return scan_for_aranet4_devices(duration)
