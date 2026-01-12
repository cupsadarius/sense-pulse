"""Aranet4 CO2 sensor communication via aranet4 package

Uses direct BLE connections to avoid DBus connection exhaustion.
See: https://github.com/hbldh/bleak/issues/1475
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Optional

from ..web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="aranet4")


class Aranet4Device:
    """Aranet4 BLE device manager.

    Owns the BLE lock and provides scan/read operations.
    Should be instantiated once on AppContext.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._sensors: dict[str, Aranet4Sensor] = {}

    def add_sensor(self, label: str, sensor: "Aranet4Sensor") -> None:
        """Register a sensor with this device manager."""
        self._sensors[label] = sensor

    def get_sensor(self, label: str) -> Optional["Aranet4Sensor"]:
        """Get a sensor by label."""
        return self._sensors.get(label)

    @property
    def sensors(self) -> dict[str, "Aranet4Sensor"]:
        """Get all registered sensors."""
        return self._sensors

    async def read_sensor(self, sensor: "Aranet4Sensor") -> Optional["Aranet4Reading"]:
        """Read from a sensor, coordinating BLE access."""
        async with self._lock:
            return await sensor.read()

    async def read_all_sensors(self) -> dict[str, Optional["Aranet4Reading"]]:
        """Read from all registered sensors."""
        results: dict[str, Optional[Aranet4Reading]] = {}
        async with self._lock:
            for label, sensor in self._sensors.items():
                results[label] = await sensor.read()
        return results

    async def scan_for_devices(self, duration: int = 10) -> list[dict[str, Any]]:
        """Scan for Aranet4 devices in range.

        Args:
            duration: Duration of scan in seconds

        Returns:
            List of discovered devices with their info
        """
        try:
            import aranet4

            logger.info("Starting Aranet4 discovery scan", duration=duration)

            found_devices: list[dict[str, Any]] = []
            seen_addresses: set[str] = set()

            def on_detect(advertisement: Any) -> None:
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

            async with self._lock:
                await aranet4.client._find_nearby(on_detect, duration=duration)

            logger.info("Aranet4 scan complete", devices_found=len(found_devices))
            return found_devices

        except ImportError:
            logger.error("aranet4 package not installed")
            return []
        except Exception as e:
            logger.error("BLE scan error", error=str(e))
            return []


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

    async def read(self) -> Optional[Aranet4Reading]:
        """Read current data from device via direct BLE connection.

        Returns:
            Aranet4Reading if successful, None if connection failed
        """
        try:
            import aranet4

            logger.info("Connecting to Aranet4 device", mac_address=self.mac_address)
            current = await aranet4.client._current_reading(self.mac_address)

            reading = Aranet4Reading(
                co2=current.co2,
                temperature=round(current.temperature, 1),
                humidity=current.humidity,
                pressure=round(current.pressure, 1),
                battery=current.battery,
                interval=current.interval,
                ago=current.ago,
                timestamp=time.time(),
            )

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

            return reading

        except ImportError:
            logger.error("aranet4 package not installed")
            self._last_error = "aranet4 package not installed"
            return None
        except Exception as e:
            logger.warning(
                "Failed to read Aranet4 device",
                mac_address=self.mac_address,
                error=str(e),
            )
            self._last_error = str(e)
            return None

    def get_cached_reading(self) -> Optional[Aranet4Reading]:
        """Get cached reading. Does NOT trigger BLE connection."""
        return self._cached_reading

    def get_co2(self) -> Optional[int]:
        """Get cached CO2 level in ppm"""
        reading = self._cached_reading
        return reading.co2 if reading else None

    def get_status(self) -> dict[str, Any]:
        """Get sensor status including last reading and any errors"""
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
