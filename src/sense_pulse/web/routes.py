"""API routes for status data"""

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from sense_pulse.cache import get_cache
from sense_pulse.devices import aranet4, sensehat
from sense_pulse.config import Config, find_config_file, load_config
from sense_pulse.web.auth import AuthConfig as WebAuthConfig
from sense_pulse.web.auth import require_auth, set_auth_config

router = APIRouter()


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


class ConfigUpdate(BaseModel):
    display: Optional[DisplayConfigUpdate] = None
    sleep: Optional[SleepConfigUpdate] = None
    aranet4: Optional[Aranet4ConfigUpdate] = None


# Lazy-initialized shared instances
_config: Optional[Config] = None
_config_path: Optional[Path] = None


def get_config():
    """Get or initialize configuration"""
    global _config, _config_path
    if _config is None:
        _config_path = find_config_file()
        _config = load_config()
        # Initialize hardware settings from config
        sensehat.set_web_rotation_offset(_config.display.web_rotation_offset)
        # Initialize Aranet4 sensors from config
        sensors_config = [
            {
                "label": sensor.label,
                "mac_address": sensor.mac_address,
                "enabled": sensor.enabled,
            }
            for sensor in _config.aranet4.sensors
        ]
        sensehat.init_aranet4_sensors(
            sensors=sensors_config,
            timeout=_config.aranet4.timeout,
            cache_duration=_config.aranet4.cache_duration,
        )

        # Initialize auth configuration
        auth_config = WebAuthConfig(
            enabled=_config.auth.enabled,
            username=_config.auth.username,
            password_hash=_config.auth.password_hash,
        )
        set_auth_config(auth_config)

    return _config


def reload_config():
    """Reload configuration from file"""
    global _config
    _config = load_config(str(_config_path) if _config_path else None)
    return _config


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, username: str = Depends(require_auth)):
    """Render main dashboard (requires authentication)"""
    templates = request.app.state.templates
    config = get_config()
    cache = await get_cache()

    # Convert aranet4 sensors to dicts for JSON serialization
    aranet4_sensors_dict = [asdict(sensor) for sensor in config.aranet4.sensors]

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "sense_hat_available": sensehat.is_sense_hat_available(),
            "aranet4_available": sensehat.is_aranet4_available(),
            "config": config,
            "aranet4_sensors": aranet4_sensors_dict,
            "tailscale": await cache.get("tailscale", {}),
            "pihole": await cache.get("pihole", {}),
            "system": await cache.get("system", {}),
            "sensors": await cache.get("sensors", {}),
            "co2": await cache.get("co2", {}),
            "aranet4_status": sensehat.get_aranet4_status(),
        },
    )


@router.get("/api/status")
async def get_status(username: str = Depends(require_auth)) -> dict[str, Any]:
    """Get all status data as JSON (from cache) - requires authentication"""
    config = get_config()
    cache = await get_cache()

    return {
        "tailscale": await cache.get("tailscale", {}),
        "pihole": await cache.get("pihole", {}),
        "system": await cache.get("system", {}),
        "sensors": await cache.get("sensors", {}),
        "co2": await cache.get("co2", {}),
        "hardware": {
            "sense_hat_available": sensehat.is_sense_hat_available(),
            "aranet4_available": sensehat.is_aranet4_available(),
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
    cache = await get_cache()
    return await cache.get("sensors", {})


@router.get("/api/status/cards", response_class=HTMLResponse)
async def get_status_cards(request: Request):
    """HTMX partial: status cards grid (from cache)"""
    config = get_config()
    templates = request.app.state.templates
    cache = await get_cache()

    return templates.TemplateResponse(
        "partials/status_cards.html",
        {
            "request": request,
            "tailscale": await cache.get("tailscale", {}),
            "pihole": await cache.get("pihole", {}),
            "system": await cache.get("system", {}),
            "sensors": await cache.get("sensors", {}),
            "co2": await cache.get("co2", {}),
            "sense_hat_available": sensehat.is_sense_hat_available(),
            "aranet4_available": sensehat.is_aranet4_available(),
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
    get_config()  # Ensure config is initialized

    try:
        while True:
            # Send only grid/matrix data for smooth animation
            data = {
                "matrix": await sensehat.get_matrix_state(),
                "hardware": {
                    "sense_hat_available": sensehat.is_sense_hat_available(),
                    "aranet4_available": sensehat.is_aranet4_available(),
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
    get_config()  # Ensure config is initialized
    cache = await get_cache()

    try:
        while True:
            # Gather all sensor data
            data = {
                "tailscale": await cache.get("tailscale", {}),
                "pihole": await cache.get("pihole", {}),
                "system": await cache.get("system", {}),
                "sensors": await cache.get("sensors", {}),
                "co2": await cache.get("co2", {}),
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
    config = get_config()
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
    }


@router.post("/api/config")
async def update_config_endpoint(
    request: Request, username: str = Depends(require_auth)
) -> dict[str, Any]:
    """Update configuration and persist to config.yaml - requires authentication"""
    global _config

    if _config_path is None or not _config_path.exists():
        return {"status": "error", "message": "No config file found"}

    try:
        # Parse JSON body
        body = await request.json()

        # Load current config file
        with open(_config_path) as f:
            config_data = yaml.safe_load(f) or {}

        # Apply updates from JSON body
        if "display" in body:
            if "display" not in config_data:
                config_data["display"] = {}
            display_updates = body["display"]

            if "rotation" in display_updates:
                rotation = int(display_updates["rotation"])
                if rotation in [0, 90, 180, 270]:
                    config_data["display"]["rotation"] = rotation
                    await sensehat.set_rotation(rotation)

            if "show_icons" in display_updates:
                config_data["display"]["show_icons"] = bool(display_updates["show_icons"])

            if "scroll_speed" in display_updates:
                config_data["display"]["scroll_speed"] = display_updates["scroll_speed"]

            if "icon_duration" in display_updates:
                config_data["display"]["icon_duration"] = display_updates["icon_duration"]

            if "web_rotation_offset" in display_updates:
                offset = int(display_updates["web_rotation_offset"])
                if offset in [0, 90, 180, 270]:
                    config_data["display"]["web_rotation_offset"] = offset
                    sensehat.set_web_rotation_offset(offset)

        if "sleep" in body:
            if "sleep" not in config_data:
                config_data["sleep"] = {}
            sleep_updates = body["sleep"]

            if "start_hour" in sleep_updates:
                config_data["sleep"]["start_hour"] = sleep_updates["start_hour"]

            if "end_hour" in sleep_updates:
                config_data["sleep"]["end_hour"] = sleep_updates["end_hour"]

            if "disable_pi_leds" in sleep_updates:
                config_data["sleep"]["disable_pi_leds"] = bool(sleep_updates["disable_pi_leds"])

        # Write back to file
        with open(_config_path, "w") as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

        # Reload config
        _config = reload_config()

        # Return success with full config state
        return {
            "status": "success",
            "config": {
                "rotation": _config.display.rotation,
                "show_icons": _config.display.show_icons,
                "web_rotation_offset": _config.display.web_rotation_offset,
                "disable_pi_leds": _config.sleep.disable_pi_leds,
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
    return {
        "status": sensehat.get_aranet4_status(),
        "data": await sensehat.get_aranet4_data(),
        "available": sensehat.is_aranet4_available(),
    }


@router.get("/api/aranet4/data")
async def get_aranet4_data() -> dict[str, Any]:
    """Get CO2 sensor readings from Aranet4 devices (from cache)"""
    cache = await get_cache()
    return await cache.get("co2", {})


@router.post("/api/aranet4/config")
async def update_aranet4_config(
    request: Request, username: str = Depends(require_auth)
) -> dict[str, Any]:
    """Update all Aranet4 sensor configurations - requires authentication"""
    global _config

    if _config_path is None or not _config_path.exists():
        return {"status": "error", "message": "No config file found"}

    try:
        # Parse JSON body with list of sensors
        body = await request.json()
        sensors = body.get("sensors", [])

        # Load current config file
        with open(_config_path) as f:
            config_data = yaml.safe_load(f) or {}

        # Ensure aranet4 section exists
        if "aranet4" not in config_data:
            config_data["aranet4"] = {}

        # Update sensors list
        config_data["aranet4"]["sensors"] = sensors

        # Write back to file
        with open(_config_path, "w") as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

        # Reload config
        _config = reload_config()

        # Update hardware sensors
        timeout = _config.aranet4.timeout
        cache_duration = _config.aranet4.cache_duration
        sensehat.update_aranet4_sensors(
            sensors=sensors,
            timeout=timeout,
            cache_duration=cache_duration,
        )

        # Return success with updated config
        return {
            "status": "success",
            "message": f"Updated {len(sensors)} sensor(s)",
            "sensors": sensors,
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/aranet4/controls", response_class=HTMLResponse)
async def get_aranet4_controls(request: Request):
    """HTMX partial: Aranet4 sensor controls panel"""
    config = get_config()
    templates = request.app.state.templates

    # Convert aranet4 sensors to dicts for JSON serialization
    aranet4_sensors_dict = [asdict(sensor) for sensor in config.aranet4.sensors]

    return templates.TemplateResponse(
        "partials/aranet4_controls.html",
        {
            "request": request,
            "config": config,
            "aranet4_sensors": aranet4_sensors_dict,
            "aranet4_status": sensehat.get_aranet4_status(),
        },
    )
