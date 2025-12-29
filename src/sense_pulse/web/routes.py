"""API routes for status data"""

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Any, Optional

import yaml
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from sense_pulse.config import load_config, find_config_file, Config
from sense_pulse.pihole import PiHoleStats
from sense_pulse.tailscale import TailscaleStatus
from sense_pulse.system import SystemStats
from sense_pulse import hardware
from sense_pulse.cache import get_cache

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
_pihole: Optional[PiHoleStats] = None
_tailscale: Optional[TailscaleStatus] = None
_system: Optional[SystemStats] = None
_config: Optional[Config] = None
_config_path: Optional[Path] = None


def get_services():
    """Get or initialize service instances"""
    global _pihole, _tailscale, _system, _config, _config_path
    if _config is None:
        _config_path = find_config_file()
        _config = load_config()
        _pihole = PiHoleStats(_config.pihole.host, _config.pihole.password)
        _tailscale = TailscaleStatus(_config.tailscale.cache_duration)
        _system = SystemStats()
        # Initialize hardware settings from config
        hardware.set_web_rotation_offset(_config.display.web_rotation_offset)
        # Initialize Aranet4 sensors from config
        hardware.init_aranet4_sensors(
            office_mac=_config.aranet4.office.mac_address,
            bedroom_mac=_config.aranet4.bedroom.mac_address,
            office_enabled=_config.aranet4.office.enabled,
            bedroom_enabled=_config.aranet4.bedroom.enabled,
            timeout=_config.aranet4.timeout,
            cache_duration=_config.aranet4.cache_duration,
        )

        # Register data sources with cache for background polling
        cache = get_cache()
        cache.register_source("tailscale", _tailscale.get_status_summary)
        cache.register_source("pihole", _pihole.get_summary)
        cache.register_source("system", _system.get_stats)
        cache.register_source("sensors", hardware.get_sensor_data)
        cache.register_source("co2", hardware.get_aranet4_data)

    return _pihole, _tailscale, _system, _config


def reload_config():
    """Reload configuration from file"""
    global _config
    _config = load_config(str(_config_path) if _config_path else None)
    return _config


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render main dashboard"""
    templates = request.app.state.templates
    _, _, _, config = get_services()
    cache = get_cache()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "sense_hat_available": hardware.is_sense_hat_available(),
        "aranet4_available": hardware.is_aranet4_available(),
        "config": config,
        "tailscale": cache.get("tailscale", {}),
        "pihole": cache.get("pihole", {}),
        "system": cache.get("system", {}),
        "sensors": cache.get("sensors", {}),
        "co2": cache.get("co2", {}),
        "aranet4_status": hardware.get_aranet4_status(),
    })


@router.get("/api/status")
async def get_status() -> Dict[str, Any]:
    """Get all status data as JSON (from cache)"""
    _, _, _, config = get_services()
    cache = get_cache()

    return {
        "tailscale": cache.get("tailscale", {}),
        "pihole": cache.get("pihole", {}),
        "system": cache.get("system", {}),
        "sensors": cache.get("sensors", {}),
        "co2": cache.get("co2", {}),
        "hardware": {
            "sense_hat_available": hardware.is_sense_hat_available(),
            "aranet4_available": hardware.is_aranet4_available(),
        },
        "config": {
            "show_icons": config.display.show_icons,
            "rotation": config.display.rotation,
            "sleep_start": config.sleep.start_hour,
            "sleep_end": config.sleep.end_hour,
        }
    }


@router.get("/api/sensors")
async def get_sensors() -> Dict[str, Any]:
    """Get Sense HAT sensor readings (from cache)"""
    cache = get_cache()
    return cache.get("sensors", {})


@router.get("/api/status/cards", response_class=HTMLResponse)
async def get_status_cards(request: Request):
    """HTMX partial: status cards grid (from cache)"""
    _, _, _, config = get_services()
    templates = request.app.state.templates
    cache = get_cache()

    return templates.TemplateResponse("partials/status_cards.html", {
        "request": request,
        "tailscale": cache.get("tailscale", {}),
        "pihole": cache.get("pihole", {}),
        "system": cache.get("system", {}),
        "sensors": cache.get("sensors", {}),
        "co2": cache.get("co2", {}),
        "sense_hat_available": hardware.is_sense_hat_available(),
        "aranet4_available": hardware.is_aranet4_available(),
        "config": config,
    })


@router.post("/api/display/clear")
async def clear_display():
    """Clear the LED matrix (no-op if Sense HAT unavailable)"""
    return hardware.clear_display()


@router.get("/api/hardware/status")
async def hardware_status():
    """Check hardware availability"""
    return {
        "sense_hat": hardware.is_sense_hat_available(),
    }


@router.get("/health")
async def health_check():
    """Health check endpoint - always succeeds even without Sense HAT"""
    return {
        "status": "healthy",
        "sense_hat_available": hardware.is_sense_hat_available(),
    }


# ============================================================================
# WebSocket Endpoints
# ============================================================================

@router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time dashboard updates (sensor data + matrix)"""
    await websocket.accept()
    get_services()  # Ensure services are initialized
    cache = get_cache()
    _, _, _, config = get_services()

    try:
        while True:
            # Gather all dashboard data
            # Reload config to get latest changes
            _, _, _, config = get_services()

            data = {
                "tailscale": cache.get("tailscale", {}),
                "pihole": cache.get("pihole", {}),
                "system": cache.get("system", {}),
                "sensors": cache.get("sensors", {}),
                "co2": cache.get("co2", {}),
                "matrix": hardware.get_matrix_state(),
                "hardware": {
                    "sense_hat_available": hardware.is_sense_hat_available(),
                    "aranet4_available": hardware.is_aranet4_available(),
                },
                "config": {
                    "show_icons": config.display.show_icons,
                    "rotation": config.display.rotation,
                    "web_rotation_offset": config.display.web_rotation_offset,
                    "disable_pi_leds": config.sleep.disable_pi_leds,
                }
            }

            await websocket.send_json(data)
            await asyncio.sleep(0.5)  # Update every 500ms for smooth matrix + real-time data
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# ============================================================================
# Configuration API
# ============================================================================

@router.get("/api/config")
async def get_config() -> Dict[str, Any]:
    """Get current configuration"""
    _, _, _, config = get_services()
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
async def update_config(updates: ConfigUpdate) -> Dict[str, Any]:
    """Update configuration and persist to config.yaml"""
    global _config

    if _config_path is None or not _config_path.exists():
        return {"status": "error", "message": "No config file found"}

    try:
        # Load current config file
        with open(_config_path) as f:
            config_data = yaml.safe_load(f) or {}

        # Apply updates
        if updates.display:
            if "display" not in config_data:
                config_data["display"] = {}
            if updates.display.rotation is not None:
                config_data["display"]["rotation"] = updates.display.rotation
            if updates.display.show_icons is not None:
                config_data["display"]["show_icons"] = updates.display.show_icons
            if updates.display.scroll_speed is not None:
                config_data["display"]["scroll_speed"] = updates.display.scroll_speed
            if updates.display.icon_duration is not None:
                config_data["display"]["icon_duration"] = updates.display.icon_duration
            if updates.display.web_rotation_offset is not None:
                config_data["display"]["web_rotation_offset"] = updates.display.web_rotation_offset
                # Also update hardware immediately
                hardware.set_web_rotation_offset(updates.display.web_rotation_offset)

        if updates.sleep:
            if "sleep" not in config_data:
                config_data["sleep"] = {}
            if updates.sleep.start_hour is not None:
                config_data["sleep"]["start_hour"] = updates.sleep.start_hour
            if updates.sleep.end_hour is not None:
                config_data["sleep"]["end_hour"] = updates.sleep.end_hour
            if updates.sleep.disable_pi_leds is not None:
                config_data["sleep"]["disable_pi_leds"] = updates.sleep.disable_pi_leds

        # Write back to file
        with open(_config_path, "w") as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

        # Reload config
        _config = reload_config()

        return {"status": "ok", "message": "Configuration updated"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/config/display/rotation")
async def set_rotation(request: Request) -> Dict[str, Any]:
    """Set display rotation"""
    form = await request.form()
    rotation = int(form.get("rotation", 0))

    # Validate rotation value
    if rotation not in [0, 90, 180, 270]:
        rotation = 0

    # Update config
    result = await update_config(ConfigUpdate(
        display=DisplayConfigUpdate(rotation=rotation)
    ))

    # Also update hardware if available
    hardware.set_rotation(rotation)

    # Return JSON with updated config
    _, _, _, config = get_services()
    return {
        **result,
        "config": {
            "rotation": config.display.rotation,
            "show_icons": config.display.show_icons,
            "web_rotation_offset": config.display.web_rotation_offset,
            "disable_pi_leds": config.sleep.disable_pi_leds,
        }
    }


@router.post("/api/config/display/icons")
async def toggle_icons(request: Request) -> Dict[str, Any]:
    """Toggle show_icons setting"""
    _, _, _, config = get_services()

    # Toggle current value
    new_value = not config.display.show_icons

    result = await update_config(ConfigUpdate(
        display=DisplayConfigUpdate(show_icons=new_value)
    ))

    # Re-fetch config after update
    _, _, _, config = get_services()
    return {
        **result,
        "config": {
            "rotation": config.display.rotation,
            "show_icons": config.display.show_icons,
            "web_rotation_offset": config.display.web_rotation_offset,
            "disable_pi_leds": config.sleep.disable_pi_leds,
        }
    }


@router.post("/api/config/sleep/pi-leds")
async def toggle_pi_leds(request: Request) -> Dict[str, Any]:
    """Toggle disable_pi_leds setting"""
    _, _, _, config = get_services()

    # Toggle current value
    new_value = not config.sleep.disable_pi_leds

    result = await update_config(ConfigUpdate(
        sleep=SleepConfigUpdate(disable_pi_leds=new_value)
    ))

    # Re-fetch config after update
    _, _, _, config = get_services()
    return {
        **result,
        "config": {
            "rotation": config.display.rotation,
            "show_icons": config.display.show_icons,
            "web_rotation_offset": config.display.web_rotation_offset,
            "disable_pi_leds": config.sleep.disable_pi_leds,
        }
    }


@router.post("/api/config/display/web-offset")
async def set_web_offset(request: Request) -> Dict[str, Any]:
    """Set web preview rotation offset"""
    form = await request.form()
    offset = int(form.get("web_offset", 90))

    # Validate offset value
    if offset not in [0, 90, 180, 270]:
        offset = 90

    # Update config
    result = await update_config(ConfigUpdate(
        display=DisplayConfigUpdate(web_rotation_offset=offset)
    ))

    # Return JSON with updated config
    _, _, _, config = get_services()
    return {
        **result,
        "config": {
            "rotation": config.display.rotation,
            "show_icons": config.display.show_icons,
            "web_rotation_offset": config.display.web_rotation_offset,
            "disable_pi_leds": config.sleep.disable_pi_leds,
        }
    }


# ============================================================================
# Aranet4 CO2 Sensor API
# ============================================================================

@router.get("/api/aranet4/scan")
async def scan_aranet4_devices() -> Dict[str, Any]:
    """Scan for Aranet4 devices via Bluetooth LE"""
    import concurrent.futures

    try:
        from sense_pulse.aranet4 import scan_for_aranet4_sync

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
async def get_aranet4_status() -> Dict[str, Any]:
    """Get Aranet4 sensor status and readings"""
    return {
        "status": hardware.get_aranet4_status(),
        "data": hardware.get_aranet4_data(),
        "available": hardware.is_aranet4_available(),
    }


@router.get("/api/aranet4/data")
async def get_aranet4_data() -> Dict[str, Any]:
    """Get CO2 sensor readings from Aranet4 devices (from cache)"""
    cache = get_cache()
    return cache.get("co2", {})


@router.post("/api/aranet4/config/{sensor_name}", response_class=HTMLResponse)
async def update_aranet4_sensor(request: Request, sensor_name: str):
    """Update Aranet4 sensor configuration (HTMX endpoint)"""
    global _config

    if sensor_name not in ["office", "bedroom"]:
        return HTMLResponse(content="Invalid sensor name", status_code=400)

    form = await request.form()
    mac_address = form.get("mac_address", "")
    enabled = form.get("enabled", "off") == "on"

    if _config_path is None or not _config_path.exists():
        return HTMLResponse(content="No config file found", status_code=500)

    try:
        # Load current config file
        with open(_config_path) as f:
            config_data = yaml.safe_load(f) or {}

        # Ensure aranet4 section exists
        if "aranet4" not in config_data:
            config_data["aranet4"] = {}
        if sensor_name not in config_data["aranet4"]:
            config_data["aranet4"][sensor_name] = {}

        # Update sensor config
        config_data["aranet4"][sensor_name]["mac_address"] = mac_address
        config_data["aranet4"][sensor_name]["enabled"] = enabled

        # Write back to file
        with open(_config_path, "w") as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

        # Reload config
        _config = reload_config()

        # Update hardware sensor
        timeout = _config.aranet4.timeout
        cache_duration = _config.aranet4.cache_duration
        hardware.update_aranet4_sensor(
            sensor_name=sensor_name,
            mac_address=mac_address,
            enabled=enabled,
            timeout=timeout,
            cache_duration=cache_duration,
        )

        # Return updated controls
        templates = request.app.state.templates
        return templates.TemplateResponse("partials/aranet4_controls.html", {
            "request": request,
            "config": _config,
            "aranet4_status": hardware.get_aranet4_status(),
        })

    except Exception as e:
        return HTMLResponse(content=f"Error: {str(e)}", status_code=500)


@router.get("/api/aranet4/controls", response_class=HTMLResponse)
async def get_aranet4_controls(request: Request):
    """HTMX partial: Aranet4 sensor controls panel"""
    _, _, _, config = get_services()
    templates = request.app.state.templates

    return templates.TemplateResponse("partials/aranet4_controls.html", {
        "request": request,
        "config": config,
        "aranet4_status": hardware.get_aranet4_status(),
    })
