"""Sleep schedule management for display"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class SleepSchedule:
    """Manages sleep hours for the display"""

    def __init__(self, sleep_start: int, sleep_end: int):
        """
        Initialize sleep schedule.

        Args:
            sleep_start: Hour to start sleep mode (0-23)
            sleep_end: Hour to end sleep mode (0-23)
        """
        self.sleep_start = sleep_start
        self.sleep_end = sleep_end
        logger.info(f"Sleep schedule: {sleep_start}:00 - {sleep_end}:00")

    def is_sleep_time(self) -> bool:
        """Check if current time is within sleep hours"""
        current_hour = datetime.now().hour

        if self.sleep_start < self.sleep_end:
            # Sleep period doesn't cross midnight (e.g., 13:00-15:00)
            is_sleeping = self.sleep_start <= current_hour < self.sleep_end
        else:
            # Sleep period crosses midnight (e.g., 22:00-07:00)
            is_sleeping = current_hour >= self.sleep_start or current_hour < self.sleep_end

        if is_sleeping:
            logger.debug(f"Sleep time active (current hour: {current_hour})")

        return is_sleeping
