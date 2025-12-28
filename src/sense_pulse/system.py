"""System statistics (CPU, memory, load)"""

import logging
import os
from typing import Dict

import psutil

logger = logging.getLogger(__name__)


class SystemStats:
    """Provides system resource statistics"""

    def get_stats(self) -> Dict[str, float]:
        """
        Get current system statistics.

        Returns:
            Dict with cpu_percent, memory_percent, and load_1min
        """
        try:
            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory().percent
            load = os.getloadavg()[0]

            logger.debug(
                f"System stats - CPU: {cpu:.1f}%, "
                f"Memory: {memory:.1f}%, Load: {load:.2f}"
            )

            return {
                "cpu_percent": round(cpu, 1),
                "memory_percent": round(memory, 1),
                "load_1min": round(load, 2),
            }
        except Exception as e:
            logger.error(f"Failed to get system stats: {e}")
            return {
                "cpu_percent": 0.0,
                "memory_percent": 0.0,
                "load_1min": 0.0,
            }
