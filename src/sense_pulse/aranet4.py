"""Aranet4 CO2 sensor communication via aranetctl CLI scan"""

import logging
import re
import subprocess
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
_scan_duration = 10  # seconds for BLE scan


def _parse_scan_output(output: str) -> Dict[str, Aranet4Reading]:
    """
    Parse aranetctl --scan output into readings by MAC address.

    Example format:
    =======================================
      Name:     Aranet4 25A3E
      Address:  C0:06:A0:90:7C:59
      RSSI:     -75 dBm
    ---------------------------------------
      CO2:            2096 ppm
      Temperature:    22.8 °C
      Humidity:       40 %
      Pressure:       960.6 hPa
      Battery:        49 %
      Status Display: RED
      Age:            211/300 s
    """
    readings: Dict[str, Aranet4Reading] = {}

    # Split by device separator
    device_blocks = re.split(r'={30,}', output)

    for block in device_blocks:
        if not block.strip():
            continue

        # Extract address
        addr_match = re.search(r'Address:\s*([0-9A-Fa-f:]+)', block)
        if not addr_match:
            continue
        address = addr_match.group(1).upper()

        # Extract readings
        co2_match = re.search(r'CO2:\s*(\d+)', block)
        temp_match = re.search(r'Temperature:\s*([\d.]+)', block)
        humidity_match = re.search(r'Humidity:\s*(\d+)', block)
        pressure_match = re.search(r'Pressure:\s*([\d.]+)', block)
        battery_match = re.search(r'Battery:\s*(\d+)', block)
        age_match = re.search(r'Age:\s*(\d+)/(\d+)', block)

        if not all([co2_match, temp_match, humidity_match, pressure_match, battery_match]):
            logger.warning(f"Incomplete data for device {address}")
            continue

        interval = 300
        ago = 0
        if age_match:
            ago = int(age_match.group(1))
            interval = int(age_match.group(2))

        readings[address] = Aranet4Reading(
            co2=int(co2_match.group(1)),
            temperature=round(float(temp_match.group(1)), 1),
            humidity=int(humidity_match.group(1)),
            pressure=round(float(pressure_match.group(1)), 1),
            battery=int(battery_match.group(1)),
            interval=interval,
            ago=ago,
            timestamp=time.time(),
        )

    return readings


def _do_scan() -> Dict[str, Aranet4Reading]:
    """Run aranetctl --scan and return readings by MAC address"""
    try:
        logger.info("Aranet4: Running BLE scan...")

        result = subprocess.run(
            ["aranetctl", "--scan"],
            capture_output=True,
            text=True,
            timeout=_scan_duration + 15,
        )

        if result.returncode != 0:
            logger.warning(f"Aranet4 scan error: {result.stderr.strip()}")
            return {}

        readings = _parse_scan_output(result.stdout)
        logger.info(f"Aranet4: Scan found {len(readings)} device(s)")
        return readings

    except subprocess.TimeoutExpired:
        logger.error("Aranet4: Scan timeout")
        return {}
    except FileNotFoundError:
        logger.error("Aranet4: aranetctl not found")
        return {}
    except Exception as e:
        logger.error(f"Aranet4: Scan error: {e}")
        return {}


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


def scan_for_aranet4_devices(duration: int = 10) -> List[Dict[str, Any]]:
    """Scan for Aranet4 devices in range using aranetctl CLI."""
    try:
        logger.info(f"Scanning for Aranet4 devices ({duration}s)...")

        result = subprocess.run(
            ["aranetctl", "--scan"],
            capture_output=True,
            text=True,
            timeout=duration + 15,
        )

        if result.returncode != 0:
            logger.warning(f"Scan CLI error: {result.stderr.strip()}")
            return []

        # Parse scan output
        found_devices = []
        device_blocks = re.split(r'={30,}', result.stdout)

        for block in device_blocks:
            if not block.strip():
                continue

            addr_match = re.search(r'Address:\s*([0-9A-Fa-f:]+)', block)
            name_match = re.search(r'Name:\s*(.+)', block)
            rssi_match = re.search(r'RSSI:\s*(-?\d+)', block)
            co2_match = re.search(r'CO2:\s*(\d+)', block)
            temp_match = re.search(r'Temperature:\s*([\d.]+)', block)
            humidity_match = re.search(r'Humidity:\s*(\d+)', block)

            if addr_match:
                device = {
                    "address": addr_match.group(1).upper(),
                    "name": name_match.group(1).strip() if name_match else "Aranet4",
                }
                if rssi_match:
                    device["rssi"] = int(rssi_match.group(1))
                if co2_match:
                    device["co2"] = int(co2_match.group(1))
                if temp_match:
                    device["temperature"] = float(temp_match.group(1))
                if humidity_match:
                    device["humidity"] = int(humidity_match.group(1))
                found_devices.append(device)

        logger.info(f"Scan complete: found {len(found_devices)} Aranet4 device(s)")
        return found_devices

    except subprocess.TimeoutExpired:
        logger.error("Scan timeout")
        return []
    except FileNotFoundError:
        logger.error("aranetctl not found - cannot scan")
        return []
    except Exception as e:
        logger.error(f"BLE scan error: {e}")
        return []


def scan_for_aranet4_sync(duration: int = 10) -> List[Dict[str, Any]]:
    """Synchronous scan for Aranet4 devices"""
    return scan_for_aranet4_devices(duration)
