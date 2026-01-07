"""Sleep schedule management for display"""

from datetime import datetime

from .web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="schedule")


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
        logger.info("Sleep schedule configured", start_hour=sleep_start, end_hour=sleep_end)

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
            logger.debug("Sleep time active", current_hour=current_hour)

        return is_sleeping
