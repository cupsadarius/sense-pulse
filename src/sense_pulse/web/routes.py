"""API routes for status data"""

import asyncio
import logging
from dataclasses import asdict
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from sense_pulse.cache import DataCache
from sense_pulse.config import Config
from sense_pulse.context import AppContext
from sense_pulse.devices import sensehat
from sense_pulse.web.app import get_app_context
from sense_pulse.web.auth import require_auth

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_context() -> AppContext:
    """
    Get AppContext.

    Returns:
        AppContext instance

    Raises:
        RuntimeError: If AppContext is not available
    """
    context = get_app_context()
    if not context:
        raise RuntimeError("AppContext not available. Web app must be initialized with context.")
    return context


def _get_cache() -> DataCache:
    """Get cache from AppContext."""
    return _get_context().cache


def _get_config() -> Config:
    """Get config from AppContext."""
    return _get_context().config


# Helper functions for Aranet4 DataSource access
async def _is_aranet4_available() -> bool:
    """Check if Aranet4 sensors are available (configured and have data)"""
    config = _get_config()
    # Check if any sensors are configured
    if not any(s.enabled for s in config.aranet4.sensors):
        return False
    # Check if cache has CO2 data
    cache = _get_cache()
    co2_data = await cache.get("co2", {})
    return bool(co2_data)


async def _get_aranet4_status() -> dict[str, Any]:
    """Get Aranet4 sensor status from DataSource via public API."""
    cache = _get_cache()

    # Use public API to get data source status
    status = cache.get_data_source_status("co2")
    return status if status else {}


async def _get_registered_sources() -> list[str]:
    """Get list of registered data source IDs."""
    cache = _get_cache()
    return cache.list_registered_sources()


# Pydantic models for configuration updates
class DisplayConfigUpdate(BaseModel):
    rotation: Optional[int] = None
    show_icons: Optional[bool] = None
    scroll_speed: Optional[float] = None
    icon_duration: Optional[float] = None
    web_rotation_offset: Optional[int] = None


class SleepConfigUpdate(BaseModel):
    start_hour: Optional[int] = None
    end_hour: Optional[int] = None
    disable_pi_leds: Optional[bool] = None


class Aranet4SensorUpdate(BaseModel):
    mac_address: Optional[str] = None
    enabled: Optional[bool] = None


class Aranet4ConfigUpdate(BaseModel):
    office: Optional[Aranet4SensorUpdate] = None
    bedroom: Optional[Aranet4SensorUpdate] = None
    timeout: Optional[int] = None
    cache_duration: Optional[int] = None


class CacheConfigUpdate(BaseModel):
    ttl: Optional[float] = None
    poll_interval: Optional[float] = None


class WeatherConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    location: Optional[str] = None
    cache_duration: Optional[int] = None


class ConfigUpdate(BaseModel):
    display: Optional[DisplayConfigUpdate] = None
    sleep: Optional[SleepConfigUpdate] = None
    aranet4: Optional[Aranet4ConfigUpdate] = None
    cache: Optional[CacheConfigUpdate] = None
    weather: Optional[WeatherConfigUpdate] = None


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, username: str = Depends(require_auth)):
    """Render main dashboard (requires authentication)"""
    templates = request.app.state.templates
    config = _get_config()
    cache = _get_cache()

    # Convert aranet4 sensors to dicts for JSON serialization
    aranet4_sensors_dict = [asdict(sensor) for sensor in config.aranet4.sensors]

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "sense_hat_available": sensehat.is_sense_hat_available(),
            "aranet4_available": await _is_aranet4_available(),
            "config": config,
            "aranet4_sensors": aranet4_sensors_dict,
            "tailscale": await cache.get("tailscale", {}),
            "pihole": await cache.get("pihole", {}),
            "system": await cache.get("system", {}),
            "sensors": await cache.get("sensors", {}),
            "co2": await cache.get("co2", {}),
            "weather": await cache.get("weather", {}),
            "aranet4_status": await _get_aranet4_status(),
        },
    )


@router.get("/api/status")
async def get_status(username: str = Depends(require_auth)) -> dict[str, Any]:
    """Get all status data as JSON (from cache) - requires authentication"""
    config = _get_config()
    cache = _get_cache()

    # Get data with timestamps for each source
    tailscale_data = await cache.get("tailscale", {}, include_timestamp=True)
    pihole_data = await cache.get("pihole", {}, include_timestamp=True)
    system_data = await cache.get("system", {}, include_timestamp=True)
    sensors_data = await cache.get("sensors", {}, include_timestamp=True)
    co2_data = await cache.get("co2", {}, include_timestamp=True)
    weather_data = await cache.get("weather", {}, include_timestamp=True)

    return {
        "tailscale": (
            tailscale_data.get("data", {}) if isinstance(tailscale_data, dict) else tailscale_data
        ),
        "pihole": pihole_data.get("data", {}) if isinstance(pihole_data, dict) else pihole_data,
        "system": system_data.get("data", {}) if isinstance(system_data, dict) else system_data,
        "sensors": sensors_data.get("data", {}) if isinstance(sensors_data, dict) else sensors_data,
        "co2": co2_data.get("data", {}) if isinstance(co2_data, dict) else co2_data,
        "weather": weather_data.get("data", {}) if isinstance(weather_data, dict) else weather_data,
        "timestamps": {
            "tailscale": (
                tailscale_data.get("timestamp") if isinstance(tailscale_data, dict) else None
            ),
            "pihole": pihole_data.get("timestamp") if isinstance(pihole_data, dict) else None,
            "system": system_data.get("timestamp") if isinstance(system_data, dict) else None,
            "sensors": sensors_data.get("timestamp") if isinstance(sensors_data, dict) else None,
            "co2": co2_data.get("timestamp") if isinstance(co2_data, dict) else None,
            "weather": weather_data.get("timestamp") if isinstance(weather_data, dict) else None,
        },
        "hardware": {
            "sense_hat_available": sensehat.is_sense_hat_available(),
            "aranet4_available": await _is_aranet4_available(),
        },
        "config": {
            "show_icons": config.display.show_icons,
            "rotation": config.display.rotation,
            "sleep_start": config.sleep.start_hour,
            "sleep_end": config.sleep.end_hour,
        },
    }


@router.get("/api/sensors")
async def get_sensors() -> dict[str, Any]:
    """Get Sense HAT sensor readings (from cache)"""
    cache = _get_cache()
    return await cache.get("sensors", {})


@router.get("/api/status/cards", response_class=HTMLResponse)
async def get_status_cards(request: Request):
    """HTMX partial: status cards grid (from cache)"""
    config = _get_config()
    templates = request.app.state.templates
    cache = _get_cache()

    return templates.TemplateResponse(
        "partials/status_cards.html",
        {
            "request": request,
            "tailscale": await cache.get("tailscale", {}),
            "pihole": await cache.get("pihole", {}),
            "system": await cache.get("system", {}),
            "sensors": await cache.get("sensors", {}),
            "co2": await cache.get("co2", {}),
            "weather": await cache.get("weather", {}),
            "sense_hat_available": sensehat.is_sense_hat_available(),
            "aranet4_available": await _is_aranet4_available(),
            "config": config,
        },
    )


@router.post("/api/display/clear")
async def clear_display(username: str = Depends(require_auth)):
    """Clear the LED matrix (no-op if Sense HAT unavailable) - requires authentication"""
    return await sensehat.clear_display()


@router.get("/api/hardware/status")
async def hardware_status():
    """Check hardware availability"""
    return {
        "sense_hat": sensehat.is_sense_hat_available(),
    }


@router.get("/health")
async def health_check():
    """Health check endpoint - always succeeds even without Sense HAT"""
    return {
        "status": "healthy",
        "sense_hat_available": sensehat.is_sense_hat_available(),
    }


# ============================================================================
# WebSocket Endpoints
# ============================================================================


@router.websocket("/ws/grid")
async def grid_websocket(websocket: WebSocket):
    """WebSocket endpoint for LED matrix and hardware status (fast updates)"""
    await websocket.accept()

    try:
        while True:
            # Send only grid/matrix data for smooth animation
            data = {
                "matrix": await sensehat.get_matrix_state(),
                "hardware": {
                    "sense_hat_available": sensehat.is_sense_hat_available(),
                    "aranet4_available": await _is_aranet4_available(),
                },
            }

            await websocket.send_json(data)
            await asyncio.sleep(0.5)  # Update every 500ms for smooth matrix animation
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


@router.websocket("/ws/sensors")
async def sensors_websocket(websocket: WebSocket):
    """WebSocket endpoint for sensor data (slower updates - 30s)"""
    await websocket.accept()
    cache = _get_cache()

    try:
        while True:
            # Get sensor data with timestamps
            tailscale_data = await cache.get("tailscale", {}, include_timestamp=True)
            pihole_data = await cache.get("pihole", {}, include_timestamp=True)
            system_data = await cache.get("system", {}, include_timestamp=True)
            sensors_data = await cache.get("sensors", {}, include_timestamp=True)
            co2_data = await cache.get("co2", {}, include_timestamp=True)
            weather_data = await cache.get("weather", {}, include_timestamp=True)

            # Gather all sensor data
            data = {
                "tailscale": (
                    tailscale_data.get("data", {})
                    if isinstance(tailscale_data, dict)
                    else tailscale_data
                ),
                "pihole": (
                    pihole_data.get("data", {}) if isinstance(pihole_data, dict) else pihole_data
                ),
                "system": (
                    system_data.get("data", {}) if isinstance(system_data, dict) else system_data
                ),
                "sensors": (
                    sensors_data.get("data", {}) if isinstance(sensors_data, dict) else sensors_data
                ),
                "co2": co2_data.get("data", {}) if isinstance(co2_data, dict) else co2_data,
                "weather": (
                    weather_data.get("data", {}) if isinstance(weather_data, dict) else weather_data
                ),
                "timestamps": {
                    "tailscale": (
                        tailscale_data.get("timestamp")
                        if isinstance(tailscale_data, dict)
                        else None
                    ),
                    "pihole": (
                        pihole_data.get("timestamp") if isinstance(pihole_data, dict) else None
                    ),
                    "system": (
                        system_data.get("timestamp") if isinstance(system_data, dict) else None
                    ),
                    "sensors": (
                        sensors_data.get("timestamp") if isinstance(sensors_data, dict) else None
                    ),
                    "co2": co2_data.get("timestamp") if isinstance(co2_data, dict) else None,
                    "weather": (
                        weather_data.get("timestamp") if isinstance(weather_data, dict) else None
                    ),
                },
            }

            await websocket.send_json(data)
            await asyncio.sleep(30)  # Update every 30s since sensor data updates slowly
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# ============================================================================
# Configuration API
# ============================================================================


@router.get("/api/config")
async def get_config_endpoint(username: str = Depends(require_auth)) -> dict[str, Any]:
    """Get current configuration - requires authentication"""
    config = _get_config()
    return {
        "display": {
            "rotation": config.display.rotation,
            "show_icons": config.display.show_icons,
            "scroll_speed": config.display.scroll_speed,
            "icon_duration": config.display.icon_duration,
        },
        "sleep": {
            "start_hour": config.sleep.start_hour,
            "end_hour": config.sleep.end_hour,
            "disable_pi_leds": config.sleep.disable_pi_leds,
        },
        "update": {
            "interval": config.update.interval,
        },
        "cache": {
            "ttl": config.cache.ttl,
            "poll_interval": config.cache.poll_interval,
        },
        "weather": {
            "enabled": config.weather.enabled,
            "location": config.weather.location,
            "cache_duration": config.weather.cache_duration,
        },
    }


@router.post("/api/config")
async def update_config_endpoint(
    request: Request, username: str = Depends(require_auth)
) -> dict[str, Any]:
    """Update configuration and persist to config.yaml - requires authentication"""
    context = _get_context()

    if context.config_path is None or not context.config_path.exists():
        return {"status": "error", "message": "No config file found"}

    try:
        # Parse JSON body
        body = await request.json()

        # Build updates dict with validation
        updates: dict[str, Any] = {}

        if "display" in body:
            display_updates = body["display"]
            updates["display"] = {}

            if "rotation" in display_updates:
                rotation = int(display_updates["rotation"])
                if rotation in [0, 90, 180, 270]:
                    updates["display"]["rotation"] = rotation
                    await sensehat.set_rotation(rotation)

            if "show_icons" in display_updates:
                updates["display"]["show_icons"] = bool(display_updates["show_icons"])

            if "scroll_speed" in display_updates:
                updates["display"]["scroll_speed"] = display_updates["scroll_speed"]

            if "icon_duration" in display_updates:
                updates["display"]["icon_duration"] = display_updates["icon_duration"]

            if "web_rotation_offset" in display_updates:
                offset = int(display_updates["web_rotation_offset"])
                if offset in [0, 90, 180, 270]:
                    updates["display"]["web_rotation_offset"] = offset
                    sensehat.set_web_rotation_offset(offset)

        if "sleep" in body:
            sleep_updates = body["sleep"]
            updates["sleep"] = {}

            if "start_hour" in sleep_updates:
                updates["sleep"]["start_hour"] = sleep_updates["start_hour"]

            if "end_hour" in sleep_updates:
                updates["sleep"]["end_hour"] = sleep_updates["end_hour"]

            if "disable_pi_leds" in sleep_updates:
                updates["sleep"]["disable_pi_leds"] = bool(sleep_updates["disable_pi_leds"])

        if "cache" in body:
            cache_updates = body["cache"]
            updates["cache"] = {}

            if "ttl" in cache_updates:
                ttl = float(cache_updates["ttl"])
                if ttl > 0:
                    updates["cache"]["ttl"] = ttl
                    logger.warning(
                        "Cache TTL updated. Please restart the application for changes to take effect."
                    )

            if "poll_interval" in cache_updates:
                poll_interval = float(cache_updates["poll_interval"])
                if poll_interval > 0:
                    updates["cache"]["poll_interval"] = poll_interval
                    logger.warning(
                        "Cache poll interval updated. Please restart the application for changes to take effect."
                    )

        if "weather" in body:
            weather_updates = body["weather"]
            updates["weather"] = {}

            if "enabled" in weather_updates:
                updates["weather"]["enabled"] = bool(weather_updates["enabled"])
                logger.warning(
                    "Weather data source enabled/disabled. Please restart the application for changes to take effect."
                )

            if "location" in weather_updates:
                updates["weather"]["location"] = str(weather_updates["location"])
                logger.warning(
                    "Weather location updated. Please restart the application for changes to take effect."
                )

            if "cache_duration" in weather_updates:
                duration = int(weather_updates["cache_duration"])
                if duration > 0:
                    updates["weather"]["cache_duration"] = duration

        # Update config via context (writes to disk and reloads)
        config = context.update_config(updates)

        # Return success with full config state
        return {
            "status": "success",
            "config": {
                "rotation": config.display.rotation,
                "show_icons": config.display.show_icons,
                "web_rotation_offset": config.display.web_rotation_offset,
                "disable_pi_leds": config.sleep.disable_pi_leds,
            },
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================================
# Aranet4 CO2 Sensor API
# ============================================================================


@router.get("/api/aranet4/scan")
async def scan_aranet4_devices(username: str = Depends(require_auth)) -> dict[str, Any]:
    """Scan for Aranet4 devices via Bluetooth LE - requires authentication"""
    import concurrent.futures

    try:
        from sense_pulse.devices.aranet4 import scan_for_aranet4_sync

        # Run sync scan in thread pool to not block FastAPI
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(scan_for_aranet4_sync, 10)
            devices = future.result(timeout=15)

        return {
            "status": "ok",
            "devices": devices,
            "count": len(devices),
        }
    except Exception as e:
        import traceback

        traceback.print_exc()
        return {
            "status": "error",
            "message": str(e),
            "devices": [],
            "count": 0,
        }


@router.get("/api/aranet4/status")
async def get_aranet4_status() -> dict[str, Any]:
    """Get Aranet4 sensor status and readings"""
    cache = _get_cache()
    return {
        "status": await _get_aranet4_status(),
        "data": await cache.get("co2", {}),
        "available": await _is_aranet4_available(),
    }


@router.get("/api/aranet4/data")
async def get_aranet4_data() -> dict[str, Any]:
    """Get CO2 sensor readings from Aranet4 devices (from cache)"""
    cache = _get_cache()
    return await cache.get("co2", {})


@router.post("/api/aranet4/config")
async def update_aranet4_config(
    request: Request, username: str = Depends(require_auth)
) -> dict[str, Any]:
    """Update all Aranet4 sensor configurations - requires authentication"""
    context = _get_context()

    if context.config_path is None or not context.config_path.exists():
        return {"status": "error", "message": "No config file found"}

    try:
        # Parse JSON body with list of sensors
        body = await request.json()
        sensors = body.get("sensors", [])

        # Update config via context (writes to disk and reloads)
        context.update_config({"aranet4": {"sensors": sensors}})

        # NOTE: Sensor changes require application restart to take effect
        # The Aranet4DataSource is initialized at startup with the config
        logger.warning(
            "Aranet4 sensor configuration updated. Please restart the application for changes to take effect."
        )

        # Return success with updated config
        return {
            "status": "success",
            "message": f"Updated {len(sensors)} sensor(s). Restart required for changes to take effect.",
            "sensors": sensors,
            "restart_required": True,
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/aranet4/controls", response_class=HTMLResponse)
async def get_aranet4_controls(request: Request):
    """HTMX partial: Aranet4 sensor controls panel"""
    config = _get_config()
    templates = request.app.state.templates

    # Convert aranet4 sensors to dicts for JSON serialization
    aranet4_sensors_dict = [asdict(sensor) for sensor in config.aranet4.sensors]

    return templates.TemplateResponse(
        "partials/aranet4_controls.html",
        {
            "request": request,
            "config": config,
            "aranet4_sensors": aranet4_sensors_dict,
            "aranet4_status": await _get_aranet4_status(),
        },
    )
