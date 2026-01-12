"""Aranet4 CO2 sensor communication via aranet4 package

Uses BLE scanning to read sensor data from advertisements.
This is more reliable than direct connections which can fail with timeout/EOR errors.
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

    async def read_all_sensors(self) -> dict[str, Optional["Aranet4Reading"]]:
        """Read all sensors via single BLE scan (10 seconds).

        Uses passive BLE scanning to collect readings from advertisements.
        This is more reliable than direct connections.

        Returns:
            Dict mapping sensor labels to readings (None if sensor not found in scan)
        """
        if not self._sensors:
            return {}

        # Build MAC -> label lookup
        mac_to_label = {sensor.mac_address: label for label, sensor in self._sensors.items()}
        results: dict[str, Optional[Aranet4Reading]] = {label: None for label in self._sensors}

        try:
            import aranet4

            logger.info("Starting Aranet4 scan for readings", sensor_count=len(self._sensors))

            def on_detect(advertisement: Any) -> None:
                addr = advertisement.device.address.upper()
                if addr in mac_to_label and advertisement.readings:
                    label = mac_to_label[addr]
                    r = advertisement.readings
                    reading = Aranet4Reading(
                        co2=r.co2,
                        temperature=round(r.temperature, 1),
                        humidity=int(r.humidity),
                        pressure=round(r.pressure, 1),
                        battery=r.battery,
                        interval=r.interval,
                        ago=r.ago,
                        timestamp=time.time(),
                    )
                    results[label] = reading
                    logger.info(
                        "Aranet4 reading from scan",
                        sensor=label,
                        co2=reading.co2,
                        temperature=reading.temperature,
                    )

            async with self._lock:
                await aranet4.client._find_nearby(on_detect, duration=10)

            found = [label for label, reading in results.items() if reading]
            missing = [label for label, reading in results.items() if not reading]
            logger.info(
                "Aranet4 scan complete",
                found=found,
                missing=missing,
            )

            return results

        except ImportError:
            logger.error("aranet4 package not installed")
            return results
        except Exception as e:
            logger.error("BLE scan error", error=str(e))
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
    timestamp: float  # When this reading was captured

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
    """Config holder for an Aranet4 sensor.

    This class only holds configuration (MAC address, name).
    Readings are fetched via Aranet4Device.read_all_sensors() using BLE scanning.
    Caching is handled by the DataCache layer.
    """

    def __init__(self, mac_address: str, name: str = "sensor"):
        self.mac_address = mac_address.upper()
        self.name = name
