"""Hardware device interfaces

This module contains low-level hardware device implementations:
- aranet4: Aranet4 CO2 sensor BLE interface
- sensehat: Sense HAT hardware abstraction (sensors, LED matrix)
- display: Display device wrapper for Sense HAT LED matrix
"""

from sense_pulse.devices.aranet4 import Aranet4Reading, Aranet4Sensor
from sense_pulse.devices.display import SenseHatDisplay
from sense_pulse.devices.sensehat import (
    clear_display,
    get_aranet4_data,
    get_aranet4_status,
    get_matrix_state,
    get_sense_hat,
    get_sensor_data,
    init_aranet4_sensors,
    is_aranet4_available,
    is_sense_hat_available,
    set_display_mode,
    set_pixels,
    set_rotation,
    set_web_rotation_offset,
    update_aranet4_sensors,
)

__all__ = [
    # Aranet4
    "Aranet4Sensor",
    "Aranet4Reading",
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
    # Aranet4 management
    "init_aranet4_sensors",
    "update_aranet4_sensors",
    "get_aranet4_data",
    "get_aranet4_status",
    "is_aranet4_available",
    # Display
    "SenseHatDisplay",
]
