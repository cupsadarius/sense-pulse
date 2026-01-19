"""Hardware device interfaces

This module contains low-level hardware device implementations:
- aranet4: Aranet4 CO2 sensor BLE interface
- network_camera: Network camera with ONVIF discovery and RTSP streaming
- sensehat: Sense HAT hardware abstraction (sensors, LED matrix)
- display: Display device wrapper for Sense HAT LED matrix
- pihole: Pi-hole API client
- tailscale: Tailscale CLI wrapper
- system: System statistics (psutil)
"""

from sense_pulse.devices.aranet4 import (
    Aranet4Device,
    Aranet4Reading,
    Aranet4Sensor,
)
from sense_pulse.devices.display import SenseHatDisplay
from sense_pulse.devices.network_camera import (
    CameraInfo,
    NetworkCameraDevice,
    StreamStatus,
)
from sense_pulse.devices.pihole import PiHoleStats
from sense_pulse.devices.sensehat import (
    clear_display,
    get_matrix_state,
    get_sense_hat,
    get_sensor_data,
    is_sense_hat_available,
    set_display_mode,
    set_pixels,
    set_rotation,
    set_web_rotation_offset,
)
from sense_pulse.devices.system import SystemStats
from sense_pulse.devices.tailscale import TailscaleStatus

__all__ = [
    # Aranet4
    "Aranet4Device",
    "Aranet4Sensor",
    "Aranet4Reading",
    # Network Camera
    "NetworkCameraDevice",
    "CameraInfo",
    "StreamStatus",
    # Sense HAT hardware
    "is_sense_hat_available",
    "get_sense_hat",
    "get_sensor_data",
    "clear_display",
    "set_pixels",
    "set_rotation",
    "get_matrix_state",
    "set_web_rotation_offset",
    "set_display_mode",
    # Display
    "SenseHatDisplay",
    # Pi-hole
    "PiHoleStats",
    # Tailscale
    "TailscaleStatus",
    # System
    "SystemStats",
]
