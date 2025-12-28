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

router = APIRouter()


# Pydantic models for configuration updates
class DisplayConfigUpdate(BaseModel):
    rotation: Optional[int] = None
    show_icons: Optional[bool] = None
    scroll_speed: Optional[float] = None
    icon_duration: Optional[float] = None


class SleepConfigUpdate(BaseModel):
    start_hour: Optional[int] = None
    end_hour: Optional[int] = None
    disable_pi_leds: Optional[bool] = None


class ConfigUpdate(BaseModel):
    display: Optional[DisplayConfigUpdate] = None
    sleep: Optional[SleepConfigUpdate] = None


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
    return templates.TemplateResponse("index.html", {
        "request": request,
        "sense_hat_available": hardware.is_sense_hat_available(),
        "config": config,
    })


@router.get("/api/status")
async def get_status() -> Dict[str, Any]:
    """Get all status data as JSON"""
    pihole, tailscale, system, config = get_services()

    return {
        "tailscale": tailscale.get_status_summary(),
        "pihole": pihole.get_summary(),
        "system": system.get_stats(),
        "sensors": hardware.get_sensor_data(),
        "hardware": {
            "sense_hat_available": hardware.is_sense_hat_available(),
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
    """Get Sense HAT sensor readings (graceful if unavailable)"""
    return hardware.get_sensor_data()


@router.get("/api/status/cards", response_class=HTMLResponse)
async def get_status_cards(request: Request):
    """HTMX partial: status cards grid"""
    pihole, tailscale, system, _ = get_services()
    templates = request.app.state.templates

    return templates.TemplateResponse("partials/status_cards.html", {
        "request": request,
        "tailscale": tailscale.get_status_summary(),
        "pihole": pihole.get_summary(),
        "system": system.get_stats(),
        "sensors": hardware.get_sensor_data(),
        "sense_hat_available": hardware.is_sense_hat_available(),
    })


@router.post("/api/display/clear")
async def clear_display():
    """Clear the LED matrix (no-op if Sense HAT unavailable)"""
    # Update tracked state to cleared
    hardware.update_matrix_state([[0, 0, 0] for _ in range(64)], "cleared")
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
# LED Matrix WebSocket
# ============================================================================

@router.websocket("/ws/matrix")
async def matrix_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time LED matrix state updates"""
    await websocket.accept()
    try:
        while True:
            # Get current matrix state and send to client
            matrix_state = hardware.get_matrix_state()
            await websocket.send_json(matrix_state)
            await asyncio.sleep(0.5)  # Update every 500ms
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


@router.get("/api/matrix")
async def get_matrix() -> Dict[str, Any]:
    """Get current LED matrix state (polling alternative to WebSocket)"""
    return hardware.get_matrix_state()


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


@router.post("/api/config/display/rotation", response_class=HTMLResponse)
async def set_rotation(request: Request):
    """Set display rotation (HTMX endpoint)"""
    form = await request.form()
    rotation = int(form.get("rotation", 0))

    # Validate rotation value
    if rotation not in [0, 90, 180, 270]:
        rotation = 0

    # Update config
    await update_config(ConfigUpdate(
        display=DisplayConfigUpdate(rotation=rotation)
    ))

    # Also update hardware if available
    hardware.set_rotation(rotation)

    # Return updated HTML partial
    _, _, _, config = get_services()
    templates = request.app.state.templates
    return templates.TemplateResponse("partials/display_controls.html", {
        "request": request,
        "config": config,
        "sense_hat_available": hardware.is_sense_hat_available(),
    })


@router.post("/api/config/display/icons", response_class=HTMLResponse)
async def toggle_icons(request: Request):
    """Toggle show_icons setting (HTMX endpoint)"""
    _, _, _, config = get_services()

    # Toggle current value
    new_value = not config.display.show_icons

    await update_config(ConfigUpdate(
        display=DisplayConfigUpdate(show_icons=new_value)
    ))

    # Re-fetch config after update and return HTML partial
    _, _, _, config = get_services()
    templates = request.app.state.templates
    return templates.TemplateResponse("partials/display_controls.html", {
        "request": request,
        "config": config,
        "sense_hat_available": hardware.is_sense_hat_available(),
    })


@router.post("/api/config/sleep/pi-leds", response_class=HTMLResponse)
async def toggle_pi_leds(request: Request):
    """Toggle disable_pi_leds setting (HTMX endpoint)"""
    _, _, _, config = get_services()

    # Toggle current value
    new_value = not config.sleep.disable_pi_leds

    await update_config(ConfigUpdate(
        sleep=SleepConfigUpdate(disable_pi_leds=new_value)
    ))

    # Re-fetch config after update and return HTML partial
    _, _, _, config = get_services()
    templates = request.app.state.templates
    return templates.TemplateResponse("partials/display_controls.html", {
        "request": request,
        "config": config,
        "sense_hat_available": hardware.is_sense_hat_available(),
    })


@router.get("/api/config/display/controls", response_class=HTMLResponse)
async def get_display_controls(request: Request):
    """HTMX partial: display controls panel"""
    _, _, _, config = get_services()
    templates = request.app.state.templates

    return templates.TemplateResponse("partials/display_controls.html", {
        "request": request,
        "config": config,
        "sense_hat_available": hardware.is_sense_hat_available(),
    })
