"""Aranet4 BLE scanner for reading sensor data and discovering devices.

Uses passive BLE scanning via the aranet4 package to read sensor data
from advertisements. This is more reliable than direct connections.
See: https://github.com/hbldh/bleak/issues/1475
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Aranet4Reading:
    """Data from a single Aranet4 sensor advertisement."""

    co2: int  # ppm
    temperature: float  # Celsius
    humidity: int  # %
    pressure: float  # mbar
    battery: int  # %
    timestamp: float  # When this reading was captured


class Aranet4Scanner:
    """BLE scanner for Aranet4 devices.

    Provides two operations:
    - scan(): Read configured sensors by MAC address
    - discover(): Find any nearby Aranet4 devices
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def scan(
        self,
        sensors: list[dict[str, str]],
        timeout: int = 10,
    ) -> dict[str, Aranet4Reading | None]:
        """Scan for configured sensors by MAC address.

        Args:
            sensors: List of {"label": "office", "mac": "AA:BB:CC:DD:EE:FF"}
            timeout: BLE scan duration in seconds

        Returns:
            Dict mapping label -> reading (None if not found in scan)
        """
        if not sensors:
            return {}

        # Build MAC -> label lookup
        mac_to_label: dict[str, str] = {}
        for s in sensors:
            mac = s.get("mac", "").upper()
            label = s.get("label", "")
            if mac and label:
                mac_to_label[mac] = label

        results: dict[str, Aranet4Reading | None] = {label: None for label in mac_to_label.values()}
        found: set[str] = set()

        try:
            import aranet4

            logger.info(
                "Starting Aranet4 scan for %d sensors (timeout=%ds)",
                len(mac_to_label),
                timeout,
            )

            def on_detect(advertisement: Any) -> None:
                addr = advertisement.device.address.upper()
                if addr in mac_to_label and advertisement.readings and addr not in found:
                    found.add(addr)
                    label = mac_to_label[addr]
                    r = advertisement.readings
                    reading = Aranet4Reading(
                        co2=r.co2,
                        temperature=round(r.temperature, 1),
                        humidity=int(r.humidity),
                        pressure=round(r.pressure, 1),
                        battery=r.battery,
                        timestamp=time.time(),
                    )
                    results[label] = reading
                    logger.info(
                        "Aranet4 reading: sensor=%s co2=%d temp=%.1f",
                        label,
                        reading.co2,
                        reading.temperature,
                    )

            async with self._lock:
                await aranet4.client._find_nearby(on_detect, duration=timeout)

            found_labels = [l for l, r in results.items() if r is not None]
            missing_labels = [l for l, r in results.items() if r is None]
            logger.info(
                "Aranet4 scan complete: found=%s missing=%s",
                found_labels,
                missing_labels,
            )

            return results

        except ImportError:
            logger.error("aranet4 package not installed")
            return results
        except Exception as e:
            logger.error("BLE scan error: %s", e)
            return results

    async def discover(self, timeout: int = 10) -> list[dict[str, Any]]:
        """Discover any nearby Aranet4 devices via passive BLE scan.

        Args:
            timeout: BLE scan duration in seconds

        Returns:
            List of discovered devices:
            [{"name": "Aranet4 12345", "mac": "AA:BB:CC:DD:EE:FF", "rssi": -60}, ...]
        """
        try:
            import aranet4

            logger.info("Starting Aranet4 discovery scan (timeout=%ds)", timeout)

            found_devices: list[dict[str, Any]] = []
            seen_addresses: set[str] = set()

            def on_detect(advertisement: Any) -> None:
                addr = advertisement.device.address.upper()
                if addr not in seen_addresses:
                    seen_addresses.add(addr)
                    device_info: dict[str, Any] = {
                        "name": advertisement.device.name or "Aranet4",
                        "mac": addr,
                        "rssi": advertisement.rssi,
                    }
                    found_devices.append(device_info)
                    logger.info(
                        "Aranet4 device found: name=%s mac=%s",
                        device_info["name"],
                        device_info["mac"],
                    )

            async with self._lock:
                await aranet4.client._find_nearby(on_detect, duration=timeout)

            logger.info("Aranet4 discovery complete: %d devices found", len(found_devices))
            return found_devices

        except ImportError:
            logger.error("aranet4 package not installed")
            return []
        except Exception as e:
            logger.error("BLE discovery error: %s", e)
            return []
