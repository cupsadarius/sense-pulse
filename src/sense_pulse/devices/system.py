"""System statistics (CPU, memory, load)"""

import asyncio
import os

import psutil

from ..web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="system")


class SystemStats:
    """Provides system resource statistics"""

    def _get_stats_sync(self) -> dict[str, float]:
        """
        Synchronous version of get_stats (runs in thread pool).

        Returns:
            Dict with cpu_percent, memory_percent, load_1min, and cpu_temp
        """
        try:
            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory().percent
            load = os.getloadavg()[0]

            # Get CPU temperature
            cpu_temp = 0.0
            try:
                temps = psutil.sensors_temperatures()
                if "cpu_thermal" in temps:
                    cpu_temp = temps["cpu_thermal"][0].current
                elif "coretemp" in temps:
                    cpu_temp = temps["coretemp"][0].current
            except (AttributeError, KeyError, IndexError):
                # Temperature sensors not available
                pass

            result = {
                "cpu_percent": round(cpu, 1),
                "memory_percent": round(memory, 1),
                "load_1min": round(load, 2),
                "cpu_temp": round(cpu_temp, 1),
            }

            logger.debug(
                "System stats collected",
                cpu_percent=result["cpu_percent"],
                memory_percent=result["memory_percent"],
                load_1min=result["load_1min"],
                cpu_temp=result["cpu_temp"],
            )

            return result
        except Exception as e:
            logger.error("Failed to get system stats", error=str(e))
            return {
                "cpu_percent": 0.0,
                "memory_percent": 0.0,
                "load_1min": 0.0,
                "cpu_temp": 0.0,
            }

    async def get_stats(self) -> dict[str, float]:
        """
        Get current system statistics (async wrapper).

        Returns:
            Dict with cpu_percent, memory_percent, load_1min, and cpu_temp
        """
        # Run blocking psutil calls in thread pool to avoid blocking event loop
        return await asyncio.to_thread(self._get_stats_sync)
