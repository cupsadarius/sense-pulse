"""API routes for status data"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from typing import Dict, Any, Optional

from sense_pulse.config import load_config, Config
from sense_pulse.pihole import PiHoleStats
from sense_pulse.tailscale import TailscaleStatus
from sense_pulse.system import SystemStats
from sense_pulse import hardware

router = APIRouter()

# Lazy-initialized shared instances
_pihole: Optional[PiHoleStats] = None
_tailscale: Optional[TailscaleStatus] = None
_system: Optional[SystemStats] = None
_config: Optional[Config] = None


def get_services():
    """Get or initialize service instances"""
    global _pihole, _tailscale, _system, _config
    if _config is None:
        _config = load_config()
        _pihole = PiHoleStats(_config.pihole.host, _config.pihole.password)
        _tailscale = TailscaleStatus(_config.tailscale.cache_duration)
        _system = SystemStats()
    return _pihole, _tailscale, _system, _config


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render main dashboard"""
    templates = request.app.state.templates
    return templates.TemplateResponse("index.html", {
        "request": request,
        "sense_hat_available": hardware.is_sense_hat_available(),
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
