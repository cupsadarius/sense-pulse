"""8x8 LED matrix icon definitions for Sense HAT"""

from typing import List, Optional

# Color constants
O = [0, 0, 0]         # Off/Black
R = [255, 0, 0]       # Red
G = [0, 255, 0]       # Green
B = [0, 0, 255]       # Blue
W = [255, 255, 255]   # White
C = [0, 255, 255]     # Cyan
Y = [255, 255, 0]     # Yellow
OR = [255, 165, 0]    # Orange
GR = [128, 128, 128]  # Gray
LB = [0, 100, 255]    # Light Blue
DR = [139, 0, 0]      # Dark Red
M = [255, 0, 255]     # Magenta

# Icon definitions - each is a 64-element list (8x8 grid)
ICONS = {
    "tailscale_connected": [
        # Green network/link icon
        O, O, G, G, G, G, O, O,
        O, G, O, O, O, O, G, O,
        G, O, O, G, G, O, O, G,
        G, O, G, O, O, G, O, G,
        G, O, G, O, O, G, O, G,
        G, O, O, G, G, O, O, G,
        O, G, O, O, O, O, G, O,
        O, O, G, G, G, G, O, O,
    ],

    "tailscale_disconnected": [
        # Red broken link icon
        O, O, R, R, O, O, O, O,
        O, R, O, O, R, O, O, O,
        R, O, O, O, O, R, O, O,
        R, O, O, O, O, O, O, O,
        O, O, O, O, O, O, O, R,
        O, O, R, O, O, O, O, R,
        O, O, O, R, O, O, R, O,
        O, O, O, O, R, R, O, O,
    ],

    "devices": [
        # Cyan computer/device icon
        O, C, C, C, C, C, C, O,
        O, C, O, O, O, O, C, O,
        O, C, O, O, O, O, C, O,
        O, C, O, O, O, O, C, O,
        O, C, C, C, C, C, C, O,
        O, O, O, C, C, O, O, O,
        O, O, C, C, C, C, O, O,
        O, C, C, C, C, C, C, O,
    ],

    "query": [
        # Green magnifying glass
        O, O, G, G, G, O, O, O,
        O, G, O, O, O, G, O, O,
        G, O, O, O, O, O, G, O,
        G, O, O, O, O, O, G, O,
        O, G, O, O, O, G, O, O,
        O, O, G, G, G, O, O, O,
        O, O, O, O, O, G, O, O,
        O, O, O, O, O, O, G, O,
    ],

    "block": [
        # Red stop/block sign
        O, O, R, R, R, R, O, O,
        O, R, R, R, R, R, R, O,
        R, R, R, W, W, R, R, R,
        R, R, W, R, R, W, R, R,
        R, R, W, R, R, W, R, R,
        R, R, R, W, W, R, R, R,
        O, R, R, R, R, R, R, O,
        O, O, R, R, R, R, O, O,
    ],

    "pihole_shield": [
        # Green shield icon
        O, G, G, G, G, G, G, O,
        G, G, G, G, G, G, G, G,
        G, G, G, G, G, G, G, G,
        G, G, G, W, W, G, G, G,
        G, G, G, W, W, G, G, G,
        O, G, G, G, G, G, G, O,
        O, O, G, G, G, G, O, O,
        O, O, O, G, G, O, O, O,
    ],

    "thermometer": [
        # Orange thermometer
        O, O, O, OR, OR, O, O, O,
        O, O, OR, O, O, OR, O, O,
        O, O, OR, R, R, OR, O, O,
        O, O, OR, R, R, OR, O, O,
        O, O, OR, R, R, OR, O, O,
        O, OR, R, R, R, R, OR, O,
        O, OR, R, R, R, R, OR, O,
        O, O, OR, OR, OR, OR, O, O,
    ],

    "water_drop": [
        # Blue water drop
        O, O, O, LB, LB, O, O, O,
        O, O, LB, LB, LB, LB, O, O,
        O, LB, LB, LB, LB, LB, LB, O,
        LB, LB, LB, LB, LB, LB, LB, LB,
        LB, LB, LB, LB, LB, LB, LB, LB,
        LB, LB, LB, LB, LB, LB, LB, LB,
        O, LB, LB, LB, LB, LB, LB, O,
        O, O, LB, LB, LB, LB, O, O,
    ],

    "pressure_gauge": [
        # Gray gauge with white needle
        O, O, GR, GR, GR, GR, O, O,
        O, GR, O, O, O, O, GR, O,
        GR, O, O, O, O, W, O, GR,
        GR, O, O, O, W, O, O, GR,
        GR, O, O, W, O, O, O, GR,
        GR, O, O, O, O, O, O, GR,
        O, GR, O, O, O, O, GR, O,
        O, O, GR, GR, GR, GR, O, O,
    ],

    "cpu": [
        # Yellow CPU chip icon
        O, O, Y, O, O, Y, O, O,
        O, Y, Y, Y, Y, Y, Y, O,
        Y, Y, O, O, O, O, Y, Y,
        O, Y, O, Y, Y, O, Y, O,
        O, Y, O, Y, Y, O, Y, O,
        Y, Y, O, O, O, O, Y, Y,
        O, Y, Y, Y, Y, Y, Y, O,
        O, O, Y, O, O, Y, O, O,
    ],

    "memory": [
        # Cyan RAM stick icon
        C, C, C, C, C, C, C, C,
        C, O, C, O, C, O, C, O,
        C, C, C, C, C, C, C, C,
        C, C, C, C, C, C, C, C,
        O, C, O, C, O, C, O, C,
        O, C, O, C, O, C, O, C,
        O, C, O, C, O, C, O, C,
        O, O, O, O, O, O, O, O,
    ],

    "load": [
        # Magenta bar graph/meter icon
        O, O, O, O, O, O, O, M,
        O, O, O, O, O, O, M, M,
        O, O, O, O, O, M, M, M,
        O, O, O, O, M, M, M, M,
        O, O, O, M, O, M, O, M,
        O, O, M, M, O, M, O, M,
        O, M, M, M, O, M, O, M,
        M, M, M, M, O, M, O, M,
    ],
}


def get_icon(name: str) -> Optional[List[List[int]]]:
    """
    Get icon pixels by name.

    Args:
        name: Icon name (e.g., 'thermometer', 'pihole_shield')

    Returns:
        64-element list of [R, G, B] values, or None if not found
    """
    return ICONS.get(name)


def list_icons() -> List[str]:
    """Get list of available icon names"""
    return list(ICONS.keys())
