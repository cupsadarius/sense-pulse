"""Hardware device interfaces

This module contains low-level hardware device implementations:
- aranet4: Aranet4 CO2 sensor BLE interface
- sensehat_sensors: Read-only access to SenseHat environmental sensors
- sensehat_display: LED matrix display control for SenseHat
- display: High-level display wrapper for Sense HAT LED matrix
- pihole: Pi-hole API client
- tailscale: Tailscale CLI wrapper
- system: System statistics (psutil)
"""

from sense_pulse.devices.aranet4 import (
    Aranet4Reading,
    Aranet4Sensor,
    scan_for_aranet4_devices,
    scan_for_aranet4_sync,
)
from sense_pulse.devices.display import SenseHatDisplay
from sense_pulse.devices.pihole import PiHoleStats
from sense_pulse.devices.sensehat_display import SenseHatDisplayController
from sense_pulse.devices.sensehat_sensors import SenseHatSensors
from sense_pulse.devices.system import SystemStats
from sense_pulse.devices.tailscale import TailscaleStatus

__all__ = [
    # Aranet4
    "Aranet4Sensor",
    "Aranet4Reading",
    "scan_for_aranet4_devices",
    "scan_for_aranet4_sync",
    # Sense HAT - Sensors (read-only)
    "SenseHatSensors",
    # Sense HAT - Display (LED matrix control)
    "SenseHatDisplayController",
    # Display (high-level wrapper)
    "SenseHatDisplay",
    # Pi-hole
    "PiHoleStats",
    # Tailscale
    "TailscaleStatus",
    # System
    "SystemStats",
]
