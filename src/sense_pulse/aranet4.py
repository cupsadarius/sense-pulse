"""Aranet4 CO2 sensor communication via the aranet4 Python package"""

import logging
import subprocess
import time
import json
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
        """
        Initialize Aranet4 sensor connection.

        Args:
            mac_address: Bluetooth MAC address of the device
            name: Friendly name for the sensor (e.g., "office", "bedroom")
            timeout: Connection timeout in seconds
            cache_duration: How long to cache readings in seconds
        """
        self.mac_address = mac_address.upper()
        self.name = name
        self.timeout = timeout
        self.cache_duration = cache_duration
        self._cached_reading: Optional[Aranet4Reading] = None
        self._last_error: Optional[str] = None

    def _fetch_reading(self) -> Optional[Aranet4Reading]:
        """Fetch a reading from the sensor using aranetctl subprocess"""
        try:
            logger.info(f"Aranet4 {self.name}: Fetching from {self.mac_address}")

            # Use aranetctl CLI tool via subprocess to avoid asyncio conflicts
            result = subprocess.run(
                ["aranetctl", self.mac_address],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            if result.returncode != 0:
                logger.error(f"Aranet4 {self.name}: aranetctl failed: {result.stderr}")
                self._last_error = result.stderr.strip() or "aranetctl failed"
                return None

            # Parse aranetctl output
            # Format: "Aranet4 | v1.4.4 | OK | 571 ppm | 20.0 C | 43 % | 1017 hPa | 100 % | 2 min"
            output = result.stdout.strip()
            logger.debug(f"Aranet4 {self.name}: Raw output: {output}")

            parts = [p.strip() for p in output.split("|")]
            if len(parts) < 9:
                logger.error(f"Aranet4 {self.name}: Unexpected output format: {output}")
                self._last_error = "Unexpected output format"
                return None

            # Extract values
            co2_str = parts[3].replace("ppm", "").strip()
            temp_str = parts[4].replace("C", "").strip()
            humidity_str = parts[5].replace("%", "").strip()
            pressure_str = parts[6].replace("hPa", "").strip()
            battery_str = parts[7].replace("%", "").strip()
            interval_str = parts[8].replace("min", "").strip()

            reading = Aranet4Reading(
                co2=int(co2_str),
                temperature=float(temp_str),
                humidity=int(humidity_str),
                pressure=float(pressure_str),
                battery=int(battery_str),
                interval=int(interval_str) * 60,  # Convert to seconds
                ago=0,
                timestamp=time.time(),
            )

            logger.info(
                f"Aranet4 {self.name}: CO2={reading.co2}ppm, "
                f"T={reading.temperature}°C, H={reading.humidity}%, "
                f"Battery={reading.battery}%"
            )

            self._last_error = None
            return reading

        except subprocess.TimeoutExpired:
            logger.error(f"Aranet4 {self.name}: Connection timeout")
            self._last_error = "Connection timeout"
            return None
        except FileNotFoundError:
            logger.error(f"Aranet4 {self.name}: aranetctl not found")
            self._last_error = "aranetctl not found"
            return None
        except Exception as e:
            logger.error(f"Aranet4 {self.name}: Error: {e}")
            self._last_error = str(e)
            return None

    def get_reading(self) -> Optional[Aranet4Reading]:
        """
        Get current sensor reading (with caching).

        Returns cached value if within cache_duration, otherwise fetches new reading.
        """
        # Check cache
        if self._cached_reading is not None:
            age = time.time() - self._cached_reading.timestamp
            if age < self.cache_duration:
                logger.debug(
                    f"Aranet4 {self.name}: Using cached reading ({age:.0f}s old)"
                )
                return self._cached_reading

        # Fetch new reading
        reading = self._fetch_reading()
        if reading:
            self._cached_reading = reading
            self._last_error = None
        return reading

    def get_co2(self) -> Optional[int]:
        """Get current CO2 level in ppm"""
        reading = self.get_reading()
        return reading.co2 if reading else None

    def get_status(self) -> Dict[str, Any]:
        """Get sensor status including last reading and any errors"""
        reading = self._cached_reading
        return {
            "name": self.name,
            "mac_address": self.mac_address,
            "connected": reading is not None,
            "last_reading": reading.to_dict() if reading else None,
            "cache_age": (
                int(time.time() - reading.timestamp)
                if reading
                else None
            ),
            "last_error": self._last_error,
        }


def scan_for_aranet4_devices(duration: int = 10) -> List[Dict[str, Any]]:
    """
    Scan for Aranet4 devices in range using aranet4 package.

    Args:
        duration: Scan duration in seconds

    Returns:
        List of discovered devices with name, address, and readings
    """
    try:
        import aranet4

        logger.info(f"Scanning for Aranet4 devices ({duration}s)...")

        found_devices = []
        seen_addresses = set()

        def on_detect(advertisement):
            """Callback for each detected device"""
            if advertisement.device.address not in seen_addresses:
                seen_addresses.add(advertisement.device.address)
                device_info = {
                    "name": advertisement.device.name or "Aranet4",
                    "address": advertisement.device.address,
                    "rssi": advertisement.rssi,
                }
                # Include readings if available from advertisement
                if advertisement.readings:
                    device_info["co2"] = advertisement.readings.co2
                    device_info["temperature"] = advertisement.readings.temperature
                    device_info["humidity"] = advertisement.readings.humidity
                found_devices.append(device_info)
                logger.info(
                    f"Found: {device_info['name']} ({device_info['address']})"
                )

        # Use aranet4's find_nearby function
        aranet4.client.find_nearby(on_detect, duration=duration)

        logger.info(f"Scan complete: found {len(found_devices)} Aranet4 device(s)")
        return found_devices

    except ImportError:
        logger.error("aranet4 library not installed - cannot scan")
        return []
    except Exception as e:
        logger.error(f"BLE scan error: {e}")
        import traceback
        traceback.print_exc()
        return []


def scan_for_aranet4_sync(duration: int = 10) -> List[Dict[str, Any]]:
    """Synchronous scan for Aranet4 devices"""
    return scan_for_aranet4_devices(duration)
