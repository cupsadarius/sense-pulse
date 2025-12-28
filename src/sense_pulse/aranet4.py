"""Aranet4 CO2 sensor communication via the aranet4 Python package"""

import asyncio
import concurrent.futures
import logging
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
        """Fetch a reading from the sensor using aranet4 package"""

        def _do_fetch():
            """Run in separate thread with fresh event loop"""
            import aranet4

            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                logger.info(f"Aranet4 {self.name}: Connecting to {self.mac_address}")

                reading = aranet4.client.get_current_readings(self.mac_address)

                if reading is None:
                    return None

                return Aranet4Reading(
                    co2=reading.co2,
                    temperature=round(reading.temperature, 1),
                    humidity=reading.humidity,
                    pressure=round(reading.pressure, 1),
                    battery=reading.battery,
                    interval=reading.interval,
                    ago=reading.ago,
                    timestamp=time.time(),
                )
            finally:
                loop.close()

        try:
            # Run BLE operation in thread with its own event loop
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_do_fetch)
                reading = future.result(timeout=self.timeout)

                if reading:
                    logger.info(
                        f"Aranet4 {self.name}: CO2={reading.co2}ppm, "
                        f"T={reading.temperature}°C, H={reading.humidity}%, "
                        f"Battery={reading.battery}%"
                    )
                    self._last_error = None
                    return reading
                else:
                    self._last_error = "No reading returned"
                    return None

        except concurrent.futures.TimeoutError:
            logger.error(f"Aranet4 {self.name}: Connection timeout")
            self._last_error = "Connection timeout"
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
