"""Aranet4 CO2 sensor communication via aranetctl CLI"""

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
        Poll the sensor for a new reading using aranetctl CLI.
        Called by background thread only.
        """
        try:
            logger.info(f"Aranet4 {self.name}: Polling {self.mac_address}")

            # Run aranetctl CLI command
            result = subprocess.run(
                ["aranetctl", self.mac_address],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            if result.returncode != 0:
                error = result.stderr.strip() or f"Exit code {result.returncode}"
                logger.warning(f"Aranet4 {self.name}: CLI error: {error}")
                self._last_error = error
                return None

            # Parse CLI output
            output = result.stdout
            reading = self._parse_cli_output(output)

            if reading is None:
                logger.warning(f"Aranet4 {self.name}: Failed to parse output")
                self._last_error = "Failed to parse CLI output"
                return None

            logger.info(
                f"Aranet4 {self.name}: CO2={reading.co2}ppm, "
                f"T={reading.temperature}°C, H={reading.humidity}%, "
                f"Battery={reading.battery}%"
            )

            with self._lock:
                self._cached_reading = reading
                self._last_error = None

            return reading

        except subprocess.TimeoutExpired:
            logger.error(f"Aranet4 {self.name}: CLI timeout after {self.timeout}s")
            self._last_error = "Timeout"
            return None
        except FileNotFoundError:
            logger.error(f"Aranet4 {self.name}: aranetctl not found")
            self._last_error = "aranetctl not installed"
            return None
        except Exception as e:
            error_msg = str(e) if str(e) else f"{type(e).__name__}"
            logger.error(f"Aranet4 {self.name}: Poll error: {error_msg}")
            self._last_error = error_msg
            return None

    def _parse_cli_output(self, output: str) -> Optional[Aranet4Reading]:
        """Parse aranetctl CLI output into Aranet4Reading"""
        try:
            # aranetctl output format:
            # CO2: 450 ppm
            # Temperature: 22.5 C
            # Humidity: 45 %
            # Pressure: 1013.25 hPa
            # Battery: 95 %
            # Update interval: 300 s
            # Last update: 120 s

            co2_match = re.search(r"CO2:\s*(\d+)", output)
            temp_match = re.search(r"Temperature:\s*([\d.]+)", output)
            humidity_match = re.search(r"Humidity:\s*(\d+)", output)
            pressure_match = re.search(r"Pressure:\s*([\d.]+)", output)
            battery_match = re.search(r"Battery:\s*(\d+)", output)
            interval_match = re.search(r"Update interval:\s*(\d+)", output)
            ago_match = re.search(r"Last update:\s*(\d+)", output)

            if not all([co2_match, temp_match, humidity_match, pressure_match, battery_match]):
                logger.warning(f"Aranet4 {self.name}: Missing fields in output: {output[:200]}")
                return None

            return Aranet4Reading(
                co2=int(co2_match.group(1)),
                temperature=round(float(temp_match.group(1)), 1),
                humidity=int(humidity_match.group(1)),
                pressure=round(float(pressure_match.group(1)), 1),
                battery=int(battery_match.group(1)),
                interval=int(interval_match.group(1)) if interval_match else 300,
                ago=int(ago_match.group(1)) if ago_match else 0,
                timestamp=time.time(),
            )
        except Exception as e:
            logger.error(f"Aranet4 {self.name}: Parse error: {e}")
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

            # Brief delay between sensors
            if not _polling_stop_event.is_set():
                time.sleep(2)

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

        # aranetctl --scan scans for devices
        result = subprocess.run(
            ["aranetctl", "--scan", str(duration)],
            capture_output=True,
            text=True,
            timeout=duration + 10,
        )

        if result.returncode != 0:
            logger.warning(f"Scan CLI error: {result.stderr.strip()}")
            return []

        # Parse scan output - format varies, typically:
        # Name: Aranet4 12345
        # Address: C0:06:A0:90:7C:59
        # RSSI: -65
        found_devices = []
        current_device: Dict[str, Any] = {}

        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                if current_device.get("address"):
                    found_devices.append(current_device)
                    current_device = {}
                continue

            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip().lower()
                value = value.strip()

                if key == "address":
                    current_device["address"] = value
                elif key == "name":
                    current_device["name"] = value
                elif key == "rssi":
                    try:
                        current_device["rssi"] = int(value.replace("dBm", "").strip())
                    except ValueError:
                        pass

        # Don't forget last device
        if current_device.get("address"):
            found_devices.append(current_device)

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
