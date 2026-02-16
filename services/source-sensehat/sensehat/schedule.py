"""Sleep schedule management for display."""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def is_sleep_time(start_hour: int, end_hour: int) -> bool:
    """Check if current time is within sleep hours.

    Handles wrap-around (e.g., start=23, end=7 means sleep from 11pm to 7am).

    Args:
        start_hour: Hour to start sleep mode (0-23).
        end_hour: Hour to end sleep mode (0-23).

    Returns:
        True if current hour is within the sleep window.
    """
    current_hour = datetime.now().hour

    if start_hour == end_hour:
        # Same hour means no sleep window
        return False

    if start_hour < end_hour:
        # Sleep period doesn't cross midnight (e.g., 13:00-15:00)
        sleeping = start_hour <= current_hour < end_hour
    else:
        # Sleep period crosses midnight (e.g., 22:00-07:00)
        sleeping = current_hour >= start_hour or current_hour < end_hour

    if sleeping:
        logger.debug(
            "Sleep time active (hour=%d, window=%d-%d)", current_hour, start_hour, end_hour
        )

    return sleeping
