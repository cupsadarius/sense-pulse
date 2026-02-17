"""Display cycle controller -- reads data from Redis and renders on LED matrix."""

from __future__ import annotations

import logging

from sense_common.redis_client import read_all_sources

import redis.asyncio as aioredis
from sensehat.display import SenseHatDisplay
from sensehat.schedule import is_sleep_time

logger = logging.getLogger(__name__)


class DisplayController:
    """Cycles through source data on the LED matrix."""

    def __init__(
        self,
        display: SenseHatDisplay,
        sleep_start: int = 23,
        sleep_end: int = 7,
    ):
        self.display = display
        self.sleep_start = sleep_start
        self.sleep_end = sleep_end
        self.show_icons = True

    # --- weather icon mapping ---

    @staticmethod
    def _weather_icon(conditions: str) -> str:
        c = conditions.lower()
        if any(w in c for w in ("clear", "sunny")):
            return "sunny"
        if any(w in c for w in ("partly cloudy", "partly")):
            return "partly_cloudy"
        if any(w in c for w in ("overcast", "cloudy", "cloud")):
            return "cloudy"
        if any(w in c for w in ("thunder", "lightning")):
            return "thunderstorm"
        if any(w in c for w in ("rain", "drizzle", "shower")):
            return "rainy"
        if any(w in c for w in ("snow", "sleet", "blizzard")):
            return "snowy"
        if any(w in c for w in ("mist", "fog", "haze")):
            return "mist"
        return "cloudy"

    @staticmethod
    def _co2_icon(co2: int) -> str:
        if co2 < 1000:
            return "co2_good"
        if co2 < 1500:
            return "co2_moderate"
        return "co2_poor"

    @staticmethod
    def _co2_color(co2: int) -> tuple[int, int, int]:
        if co2 < 1000:
            return (0, 255, 0)
        if co2 < 1500:
            return (255, 255, 0)
        return (255, 0, 0)

    # --- per-source display methods ---

    async def _show_tailscale(self, data: dict) -> None:
        connected = data.get("connected", {}).get("value", False)
        device_count = data.get("device_count", {}).get("value", 0)
        icon = "tailscale_connected" if connected else "tailscale_disconnected"
        color = (0, 255, 0) if connected else (255, 0, 0)
        label = "Connected" if connected else "Disconnected"
        await self.display.show_icon_with_text(icon, label, text_color=color)
        if connected:
            await self.display.show_icon_with_text(
                "devices", f"{device_count} Devices", text_color=(0, 200, 255)
            )

    async def _show_pihole(self, data: dict) -> None:
        queries = data.get("queries_today", {}).get("value", 0)
        blocked = data.get("ads_blocked_today", {}).get("value", 0)
        pct = data.get("ads_percentage_today", {}).get("value", 0.0)
        await self.display.show_icon_with_text(
            "query", f"Queries: {queries}", text_color=(0, 255, 0)
        )
        await self.display.show_icon_with_text(
            "block", f"Blocked: {blocked}", text_color=(255, 0, 0)
        )
        await self.display.show_icon_with_text(
            "pihole_shield", f"{pct:.1f}% Blocked", text_color=(255, 165, 0)
        )

    async def _show_system(self, data: dict) -> None:
        cpu = data.get("cpu_percent", {}).get("value", 0.0)
        mem = data.get("memory_percent", {}).get("value", 0.0)
        load = data.get("load_1min", {}).get("value", 0.0)
        await self.display.show_icon_with_text("cpu", f"CPU: {cpu:.0f}%", text_color=(255, 200, 0))
        await self.display.show_icon_with_text(
            "memory", f"Mem: {mem:.0f}%", text_color=(0, 200, 255)
        )
        await self.display.show_icon_with_text(
            "load", f"Load: {load:.2f}", text_color=(255, 0, 255)
        )

    async def _show_sensors(self, data: dict) -> None:
        temp = data.get("temperature", {}).get("value", 0.0)
        hum = data.get("humidity", {}).get("value", 0.0)
        pres = data.get("pressure", {}).get("value", 0.0)
        await self.display.show_icon_with_text(
            "thermometer", f"{temp:.1f}C", text_color=(255, 100, 0)
        )
        await self.display.show_icon_with_text(
            "water_drop", f"{hum:.1f}%", text_color=(0, 100, 255)
        )
        await self.display.show_icon_with_text(
            "pressure_gauge", f"{pres:.0f}mb", text_color=(200, 200, 200)
        )

    async def _show_co2(self, data: dict) -> None:
        # CO2 readings are flat: {label}:{metric} e.g. "office:co2"
        # Group by label
        labels: dict[str, dict] = {}
        for key, reading in data.items():
            if ":" not in key:
                continue
            label, metric = key.split(":", 1)
            labels.setdefault(label, {})[metric] = reading.get("value")

        for label, metrics in labels.items():
            co2 = metrics.get("co2")
            temp = metrics.get("temperature")
            if co2 is not None:
                icon = self._co2_icon(int(co2))
                color = self._co2_color(int(co2))
                await self.display.show_icon_with_text(icon, f"{label}: {co2}ppm", text_color=color)
            if temp is not None:
                await self.display.show_icon_with_text(
                    "thermometer", f"{label}: {temp}C", text_color=(255, 100, 0)
                )

    async def _show_weather(self, data: dict) -> None:
        temp = data.get("weather_temp", {}).get("value")
        conditions = data.get("weather_conditions", {}).get("value", "Unknown")
        location = data.get("weather_location", {}).get("value", "")
        if temp is not None:
            icon = self._weather_icon(conditions)
            await self.display.show_icon_with_text(icon, f"{temp:.0f}C", text_color=(255, 200, 0))
        if conditions and conditions != "Unknown":
            text = f"{location}: {conditions}" if location else conditions
            await self.display.show_text(text, color=(100, 200, 255))

    # --- main cycle ---

    async def run_cycle(self, redis: aioredis.Redis) -> None:
        """Run one complete display cycle."""
        if is_sleep_time(self.sleep_start, self.sleep_end):
            await self.display.clear()
            return

        all_data = await read_all_sources(redis)

        # Cycle through sources in order, skip those with no data
        for source_id, handler in [
            ("tailscale", self._show_tailscale),
            ("pihole", self._show_pihole),
            ("system", self._show_system),
            ("sensors", self._show_sensors),
            ("co2", self._show_co2),
            ("weather", self._show_weather),
        ]:
            data = all_data.get(source_id, {})
            if data:
                try:
                    await handler(data)
                except Exception:
                    logger.exception("Error displaying %s", source_id)
