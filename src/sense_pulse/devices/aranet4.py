"""Aranet4 CO2 sensor communication via aranet4 package scan"""

import asyncio
import contextlib
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


# Background polling task
_polling_task: Optional[asyncio.Task] = None
_polling_stop_event = asyncio.Event()
_scan_lock = threading.Lock()  # Prevent concurrent BLE scans (works across async/threads)
_task_lock = threading.Lock()  # Prevent multiple polling tasks from being created
_last_scan_time: float = 0  # Track last scan time for cooldown
_scan_cooldown = 5  # Minimum seconds between scans
_sensors_to_poll: list[Aranet4Sensor] = []
_poll_interval = 30  # seconds
_scan_duration = 8  # seconds for BLE scan
_task_counter = 0  # For debugging multiple task instances


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(2),  # Only 1 retry for BLE to avoid long delays
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _do_scan() -> dict[str, Aranet4Reading]:
    """Run aranet4 package scan and return readings by MAC address (with retries)

    IMPORTANT: Must be called with _scan_lock held to prevent concurrent scans.
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

        aranet4.client.find_nearby(on_detect, duration=_scan_duration)
        logger.info(f"Aranet4: Scan found {len(readings)} device(s)")
        return readings

    except ImportError:
        logger.error("Aranet4: aranet4 package not installed")
        return {}
    except Exception as e:
        logger.warning(f"Aranet4: Scan error (may retry): {e}")
        raise


async def _polling_loop():
    """Background task that scans for all sensors at once"""
    global _task_counter
    _task_counter += 1
    task_id = _task_counter
    logger.info(f"Aranet4 background polling started (task #{task_id})")

    while not _polling_stop_event.is_set():
        try:
            # Single scan gets all devices (run in thread pool to avoid blocking)
            # Use threading lock to prevent concurrent BLE scans from any context
            logger.debug(f"Aranet4 task #{task_id}: Waiting for scan lock...")

            def locked_scan():
                """Run scan with lock held"""
                with _scan_lock:
                    logger.debug(f"Aranet4 task #{task_id}: Acquired scan lock, starting scan")
                    return _do_scan()

            readings = await asyncio.to_thread(locked_scan)

            # Update each registered sensor with its reading
            for sensor in _sensors_to_poll:
                if sensor.mac_address in readings:
                    sensor.update_reading(readings[sensor.mac_address])
                else:
                    sensor.set_error("Not found in scan")

        except Exception as e:
            logger.error(f"Aranet4 polling error (task #{task_id}): {e}")

        # Wait for next poll interval
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(_polling_stop_event.wait(), timeout=_poll_interval)

    logger.info(f"Aranet4 background polling stopped (task #{task_id})")


def register_sensor(sensor: Aranet4Sensor) -> None:
    """Register a sensor for background polling"""
    global _polling_task

    # Check by MAC address to avoid duplicate registrations from different code paths
    existing_macs = {s.mac_address for s in _sensors_to_poll}
    if sensor.mac_address not in existing_macs:
        _sensors_to_poll.append(sensor)
        logger.info(f"Registered Aranet4 sensor: {sensor.name} ({sensor.mac_address})")
    else:
        logger.debug(f"Aranet4 sensor already registered: {sensor.name} ({sensor.mac_address})")

    # Start polling task if not running (thread-safe check)
    with _task_lock:
        if _polling_task is None:
            logger.info("Starting new Aranet4 polling task (no previous task)")
            _polling_stop_event.clear()
            _polling_task = asyncio.create_task(_polling_loop())
        elif _polling_task.done():
            logger.warning(
                f"Previous Aranet4 polling task finished (done={_polling_task.done()}), starting new one"
            )
            _polling_stop_event.clear()
            _polling_task = asyncio.create_task(_polling_loop())
        else:
            logger.debug("Aranet4 polling task already running")


def unregister_sensor(sensor: Aranet4Sensor) -> None:
    """Unregister a sensor from background polling"""
    # Find and remove by MAC address to handle different object instances
    for s in list(_sensors_to_poll):
        if s.mac_address == sensor.mac_address:
            _sensors_to_poll.remove(s)
            logger.info(f"Unregistered Aranet4 sensor: {sensor.name} ({sensor.mac_address})")
            break


async def stop_polling() -> None:
    """Stop the background polling task"""
    global _polling_task
    _polling_stop_event.set()
    if _polling_task and not _polling_task.done():
        try:
            await asyncio.wait_for(_polling_task, timeout=5)
        except asyncio.TimeoutError:
            _polling_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await _polling_task
    _polling_task = None


def scan_for_aranet4_devices(duration: int = 10) -> list[dict[str, Any]]:
    """Scan for Aranet4 devices in range using aranet4 package.

    Uses global scan lock to prevent concurrent BLE operations.
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
    """Synchronous scan for Aranet4 devices"""
    return scan_for_aranet4_devices(duration)


# ============================================================================
# Sensor Registry Management
# ============================================================================

# Aranet4 CO2 sensors registry (label -> Aranet4Sensor)
_aranet4_sensors: dict[str, Aranet4Sensor] = {}
_aranet4_initialized: bool = False


def init_aranet4_sensors(
    sensors: list[dict[str, Any]] = None,
    timeout: int = 30,
    cache_duration: int = 60,
) -> None:
    """Initialize Aranet4 CO2 sensors and start background polling

    Args:
        sensors: List of sensor configs, each with 'label', 'mac_address', and 'enabled' fields
        timeout: Connection timeout in seconds (unused, kept for API compatibility)
        cache_duration: Cache duration in seconds
    """
    global _aranet4_sensors, _aranet4_initialized

    if _aranet4_initialized:
        return

    _aranet4_initialized = True

    if sensors is None:
        sensors = []

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


def update_aranet4_sensors(
    sensors: list[dict[str, Any]],
    timeout: int = 30,
    cache_duration: int = 60,
) -> dict[str, str]:
    """Update all Aranet4 sensor configurations

    NOTE: This function updates the global sensor registry for immediate effect,
    but full integration requires restarting the application to reload the
    Aranet4DataSource with the new configuration.

    Args:
        sensors: List of sensor configs, each with 'label', 'mac_address', and 'enabled' fields
        timeout: Connection timeout in seconds (unused, kept for API compatibility)
        cache_duration: Cache duration in seconds
    """
    global _aranet4_sensors

    # Unregister all existing sensors from global registry
    for sensor in list(_sensors_to_poll):
        unregister_sensor(sensor)

    # Clear legacy dict (kept for backward compatibility)
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
            _aranet4_sensors[label] = sensor  # Keep for backward compatibility
            register_sensor(sensor)
            logger.info(f"Aranet4 sensor '{label}' updated: {mac_address}")

    logger.warning(
        "Sensor configuration updated. For full effect with DataSource integration, "
        "restart the application."
    )

    return {"status": "ok", "message": f"Updated {len(_aranet4_sensors)} sensor(s)"}


async def get_aranet4_data() -> dict[str, Any]:
    """Get CO2 sensor data from cache only (does not trigger BLE)

    NOTE: This is a legacy function. Prefer using the cache with key "co2" instead.
    """
    result = {}

    for sensor in _sensors_to_poll:
        reading = sensor.get_cached_reading()
        if reading:
            result[sensor.name] = reading.to_dict()

    return result if result else {"available": False}


def get_aranet4_status() -> dict[str, Any]:
    """Get status of all Aranet4 sensors registered for polling"""
    result = {}

    for sensor in _sensors_to_poll:
        result[sensor.name] = sensor.get_status()

    return result


def is_aranet4_available() -> bool:
    """Check if any Aranet4 sensor is configured and registered for polling"""
    return len(_sensors_to_poll) > 0
