"""API routes for status data"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from sense_pulse.context import AppContext
from sense_pulse.devices import sensehat
from sense_pulse.web.app import get_context
from sense_pulse.web.auth import require_auth
from sense_pulse.web.log_handler import get_structured_logger, setup_websocket_logging

if TYPE_CHECKING:
    from sense_pulse.devices.network_camera import NetworkCameraDevice

logger = get_structured_logger(__name__, component="routes")
router = APIRouter()


# Helper functions for Aranet4 DataSource access
async def _is_aranet4_available(context: AppContext) -> bool:
    """Check if Aranet4 sensors are available (configured and have data)"""
    config = context.config
    # Check if any sensors are configured
    if not any(s.enabled for s in config.aranet4.sensors):
        return False
    # Check if cache has CO2 data
    co2_data = await context.cache.get("co2", {})
    return bool(co2_data)


async def _get_aranet4_status(context: AppContext) -> dict[str, Any]:
    """Get Aranet4 sensor status from DataSource via public API."""
    # Use public API to get data source status
    status = context.cache.get_data_source_status("co2")
    return status if status else {}


# Pydantic models for configuration updates
class DisplayConfigUpdate(BaseModel):
    rotation: int | None = None
    show_icons: bool | None = None
    scroll_speed: float | None = None
    icon_duration: float | None = None
    web_rotation_offset: int | None = None


class SleepConfigUpdate(BaseModel):
    start_hour: int | None = None
    end_hour: int | None = None
    disable_pi_leds: bool | None = None


class Aranet4SensorUpdate(BaseModel):
    mac_address: str | None = None
    enabled: bool | None = None


class Aranet4ConfigUpdate(BaseModel):
    office: Aranet4SensorUpdate | None = None
    bedroom: Aranet4SensorUpdate | None = None
    timeout: int | None = None
    cache_duration: int | None = None


class CacheConfigUpdate(BaseModel):
    ttl: float | None = None
    poll_interval: float | None = None


class WeatherConfigUpdate(BaseModel):
    enabled: bool | None = None
    location: str | None = None
    cache_duration: int | None = None


class ConfigUpdate(BaseModel):
    display: DisplayConfigUpdate | None = None
    sleep: SleepConfigUpdate | None = None
    aranet4: Aranet4ConfigUpdate | None = None
    cache: CacheConfigUpdate | None = None
    weather: WeatherConfigUpdate | None = None


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
):
    """Render main dashboard (requires authentication)"""
    templates = request.app.state.templates
    config = context.config
    cache = context.cache

    # Convert aranet4 sensors to dicts for JSON serialization
    aranet4_sensors_dict = [asdict(sensor) for sensor in config.aranet4.sensors]

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "sense_hat_available": sensehat.is_sense_hat_available(),
            "aranet4_available": await _is_aranet4_available(context),
            "network_camera_enabled": config.network_camera.enabled,
            "config": config,
            "aranet4_sensors": aranet4_sensors_dict,
            "network_camera_cameras": config.network_camera.cameras,
            "tailscale": await cache.get("tailscale", {}),
            "pihole": await cache.get("pihole", {}),
            "system": await cache.get("system", {}),
            "sensors": await cache.get("sensors", {}),
            "co2": await cache.get("co2", {}),
            "weather": await cache.get("weather", {}),
            "aranet4_status": await _get_aranet4_status(context),
            "datasource_status": cache.get_all_source_status(),
        },
    )


@router.get("/api/status")
async def get_status(
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
) -> dict[str, Any]:
    """Get all status data as JSON (from cache) - requires authentication"""
    config = context.config
    cache = context.cache

    return {
        "tailscale": await cache.get("tailscale", {}),
        "pihole": await cache.get("pihole", {}),
        "system": await cache.get("system", {}),
        "sensors": await cache.get("sensors", {}),
        "co2": await cache.get("co2", {}),
        "weather": await cache.get("weather", {}),
        "hardware": {
            "sense_hat_available": sensehat.is_sense_hat_available(),
            "aranet4_available": await _is_aranet4_available(context),
        },
        "config": {
            "show_icons": config.display.show_icons,
            "rotation": config.display.rotation,
            "sleep_start": config.sleep.start_hour,
            "sleep_end": config.sleep.end_hour,
        },
    }


@router.get("/api/sensors")
async def get_sensors(context: AppContext = Depends(get_context)) -> dict[str, Any]:
    """Get Sense HAT sensor readings (from cache)"""
    result: dict[str, Any] = await context.cache.get("sensors", {})
    return result


@router.get("/api/status/cards", response_class=HTMLResponse)
async def get_status_cards(request: Request, context: AppContext = Depends(get_context)):
    """HTMX partial: status cards grid (from cache)"""
    config = context.config
    templates = request.app.state.templates
    cache = context.cache

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
            "aranet4_available": await _is_aranet4_available(context),
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


@router.get("/api/datasources/status")
async def get_datasources_status(
    context: AppContext = Depends(get_context),
) -> list[dict[str, Any]]:
    """Get status of all data sources"""
    return context.cache.get_all_source_status()


# ============================================================================
# WebSocket Endpoints
# ============================================================================


@router.websocket("/ws/grid")
async def grid_websocket(websocket: WebSocket):
    """WebSocket endpoint for LED matrix and hardware status (fast updates)"""
    await websocket.accept()

    # Get context from app.state for WebSocket handlers
    context: AppContext = websocket.app.state.context

    try:
        while True:
            # Send only grid/matrix data for smooth animation
            data = {
                "matrix": await sensehat.get_matrix_state(),
                "hardware": {
                    "sense_hat_available": sensehat.is_sense_hat_available(),
                    "aranet4_available": await _is_aranet4_available(context),
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

    # Get context from app.state for WebSocket handlers
    context: AppContext = websocket.app.state.context
    cache = context.cache

    try:
        while True:
            # Gather all sensor data (each sensor has value and timestamp embedded)
            data = {
                "tailscale": await cache.get("tailscale", {}),
                "pihole": await cache.get("pihole", {}),
                "system": await cache.get("system", {}),
                "sensors": await cache.get("sensors", {}),
                "co2": await cache.get("co2", {}),
                "weather": await cache.get("weather", {}),
                "datasource_status": cache.get_all_source_status(),
            }

            # Include network camera status if available
            network_camera_device = _get_network_camera_device(context)
            if network_camera_device:
                data["network_camera"] = network_camera_device.get_status()

            await websocket.send_json(data)
            await asyncio.sleep(30)  # Update every 30s since sensor data updates slowly
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# Log level name to number mapping
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


@router.websocket("/ws/logs")
async def logs_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for streaming application logs.

    Query parameters:
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        history: Number of historical logs to send on connect (default: 100)
    """
    await websocket.accept()

    # Parse query parameters
    level_name = websocket.query_params.get("level", "DEBUG").upper()
    min_level = LOG_LEVELS.get(level_name, logging.DEBUG)
    history_count = int(websocket.query_params.get("history", "100"))

    # Get or setup the log handler
    log_handler = setup_websocket_logging()

    # Register this client
    await log_handler.register_client(websocket)

    try:
        # Send historical logs
        history = log_handler.get_buffer(min_level)
        if history:
            # Send only the last N logs based on history_count
            history_to_send = history[-history_count:] if len(history) > history_count else history
            await websocket.send_json(
                {
                    "type": "history",
                    "data": history_to_send,
                    "total": len(history),
                }
            )

        # Keep connection alive and listen for client messages
        while True:
            try:
                # Wait for messages from client (for level changes, etc.)
                message = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=30.0,  # Heartbeat interval
                )

                # Handle level change requests
                if message.get("type") == "set_level":
                    new_level = message.get("level", "DEBUG").upper()
                    min_level = LOG_LEVELS.get(new_level, logging.DEBUG)
                    await websocket.send_json(
                        {
                            "type": "level_changed",
                            "level": new_level,
                        }
                    )

            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                await websocket.send_json({"type": "heartbeat"})

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        # Unregister client on disconnect
        await log_handler.unregister_client(websocket)


# ============================================================================
# Configuration API
# ============================================================================


@router.get("/api/config")
async def get_config_endpoint(
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
) -> dict[str, Any]:
    """Get current configuration - requires authentication"""
    config = context.config
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
    request: Request,
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
) -> dict[str, Any]:
    """Update configuration and persist to config.yaml - requires authentication"""

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
async def scan_aranet4_devices(
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
) -> dict[str, Any]:
    """Scan for Aranet4 devices via Bluetooth LE - requires authentication"""
    try:
        if not context.aranet4_device:
            return {
                "status": "error",
                "message": "Aranet4 device not available",
                "devices": [],
                "count": 0,
            }

        devices = await context.aranet4_device.scan_for_devices(duration=10)

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
async def get_aranet4_status_endpoint(
    context: AppContext = Depends(get_context),
) -> dict[str, Any]:
    """Get Aranet4 sensor status and readings"""
    cache = context.cache
    return {
        "status": await _get_aranet4_status(context),
        "data": await cache.get("co2", {}),
        "available": await _is_aranet4_available(context),
    }


@router.get("/api/aranet4/data")
async def get_aranet4_data(context: AppContext = Depends(get_context)) -> dict[str, Any]:
    """Get CO2 sensor readings from Aranet4 devices (from cache)"""
    result: dict[str, Any] = await context.cache.get("co2", {})
    return result


@router.post("/api/aranet4/config")
async def update_aranet4_config(
    request: Request,
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
) -> dict[str, Any]:
    """Update all Aranet4 sensor configurations - requires authentication"""

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
async def get_aranet4_controls(request: Request, context: AppContext = Depends(get_context)):
    """HTMX partial: Aranet4 sensor controls panel"""
    config = context.config
    templates = request.app.state.templates

    # Convert aranet4 sensors to dicts for JSON serialization
    aranet4_sensors_dict = [asdict(sensor) for sensor in config.aranet4.sensors]

    return templates.TemplateResponse(
        "partials/aranet4_controls.html",
        {
            "request": request,
            "config": config,
            "aranet4_sensors": aranet4_sensors_dict,
            "aranet4_status": await _get_aranet4_status(context),
        },
    )


# ============================================================================
# Network Camera API
# ============================================================================


def _get_network_camera_device(context: AppContext) -> NetworkCameraDevice | None:
    """Get the network camera device from context."""
    return getattr(context, "network_camera_device", None)


@router.get("/api/network-camera/status")
async def get_network_camera_status(
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
) -> dict[str, Any]:
    """Get current network camera stream status - requires authentication."""
    device = _get_network_camera_device(context)
    if not device:
        return {
            "status": "disabled",
            "enabled": False,
            "error": "Network camera not configured",
        }
    return device.get_status()


@router.post("/api/network-camera/start")
async def start_network_camera_stream(
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
) -> dict[str, Any]:
    """Start the network camera HLS stream - requires authentication."""
    device = _get_network_camera_device(context)
    if not device:
        return {"success": False, "message": "Network camera not configured"}

    try:
        success = await device.start_stream()
        return {
            "success": success,
            "message": "Stream started" if success else "Failed to start stream",
            "status": device.get_status(),
        }
    except Exception as e:
        logger.error("Failed to start network camera stream", error=str(e))
        return {"success": False, "message": str(e)}


@router.post("/api/network-camera/stop")
async def stop_network_camera_stream(
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
) -> dict[str, Any]:
    """Stop the network camera HLS stream - requires authentication."""
    device = _get_network_camera_device(context)
    if not device:
        return {"success": False, "message": "Network camera not configured"}

    try:
        await device.stop_stream()
        return {"success": True, "message": "Stream stopped"}
    except Exception as e:
        logger.error("Failed to stop network camera stream", error=str(e))
        return {"success": False, "message": str(e)}


@router.post("/api/network-camera/restart")
async def restart_network_camera_stream(
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
) -> dict[str, Any]:
    """Restart the network camera stream - requires authentication."""
    device = _get_network_camera_device(context)
    if not device:
        return {"success": False, "message": "Network camera not configured"}

    try:
        await device.restart_stream()
        return {"success": True, "message": "Stream restarting"}
    except Exception as e:
        logger.error("Failed to restart network camera stream", error=str(e))
        return {"success": False, "message": str(e)}


@router.post("/api/network-camera/discover")
async def discover_network_cameras(
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
) -> dict[str, Any]:
    """Discover cameras by scanning network for RTSP ports - requires authentication."""
    device = _get_network_camera_device(context)
    if not device:
        return {"success": False, "cameras": [], "message": "Network camera not configured"}

    try:
        cameras = await device.discover_cameras(timeout=30)
        return {
            "success": True,
            "cameras": [
                {
                    "name": cam.name,
                    "host": cam.host,
                    "port": cam.port,
                }
                for cam in cameras
            ],
            "count": len(cameras),
        }
    except Exception as e:
        logger.error("Failed to discover cameras", error=str(e))
        return {"success": False, "cameras": [], "message": str(e)}


@router.post("/api/network-camera/config")
async def update_network_camera_config(
    request: Request,
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
) -> dict[str, Any]:
    """Update network camera configurations - requires authentication."""

    if context.config_path is None or not context.config_path.exists():
        return {"status": "error", "message": "No config file found"}

    try:
        # Parse JSON body with list of cameras
        body = await request.json()
        new_cameras = body.get("cameras", [])

        # Merge with existing cameras to preserve fields the UI doesn't manage
        existing_cameras = context.config.network_camera.cameras
        merged_cameras = []
        for i, new_cam in enumerate(new_cameras):
            if i < len(existing_cameras):
                # Preserve existing fields, update with new values
                merged = existing_cameras[i].copy()
                merged.update(new_cam)
                merged_cameras.append(merged)
            else:
                merged_cameras.append(new_cam)

        # Update config via context (writes to disk and reloads)
        context.update_config({"network_camera": {"cameras": merged_cameras}})

        # NOTE: Camera changes require application restart to take effect
        logger.warning(
            "Network camera configuration updated. "
            "Please restart the application for changes to take effect."
        )

        return {
            "status": "success",
            "message": f"Updated {len(merged_cameras)} camera(s). Restart required for changes to take effect.",
            "cameras": merged_cameras,
            "restart_required": True,
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/network-camera/thumbnail")
async def get_network_camera_thumbnail(
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
    force: bool = False,
):
    """Get a thumbnail image from the network camera - requires authentication."""
    from fastapi.responses import Response

    device = _get_network_camera_device(context)
    if not device:
        return Response(status_code=404, content=b"Network camera not configured")

    try:
        thumbnail = await device.capture_thumbnail(force=force)
        if thumbnail:
            return Response(
                content=thumbnail,
                media_type="image/jpeg",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
        return Response(status_code=503, content=b"Failed to capture thumbnail")
    except Exception as e:
        logger.error("Failed to capture thumbnail", error=str(e))
        return Response(status_code=500, content=str(e).encode())


@router.get("/api/network-camera/stream/stream.m3u8")
async def get_network_camera_hls_playlist(
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
):
    """Serve HLS playlist - requires authentication."""
    from fastapi.responses import FileResponse, JSONResponse

    device = _get_network_camera_device(context)
    if not device:
        return JSONResponse({"error": "Network camera not configured"}, status_code=404)

    playlist_path = device.playlist_path
    if not playlist_path.exists():
        return JSONResponse({"error": "Stream not ready"}, status_code=503)

    return FileResponse(
        playlist_path,
        media_type="application/vnd.apple.mpegurl",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/api/network-camera/stream/{segment_name}")
async def get_network_camera_hls_segment(
    segment_name: str,
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
):
    """Serve HLS segment - requires authentication."""
    from pathlib import Path

    from fastapi.responses import FileResponse

    device = _get_network_camera_device(context)
    if not device:
        return {"error": "Network camera not configured"}

    # Validate segment name (must be .ts file)
    if not segment_name.endswith(".ts"):
        return {"error": "Invalid segment"}

    # Sanitize path to prevent directory traversal
    segment_path = device.output_dir / Path(segment_name).name
    if not segment_path.exists():
        return {"error": "Segment not found"}

    return FileResponse(
        segment_path,
        media_type="video/mp2t",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# ============================================================================
# Network Camera PTZ Control API
# ============================================================================


class PTZMoveRequest(BaseModel):
    """Request body for PTZ move endpoint."""

    direction: str  # up, down, left, right, zoomin, zoomout
    step: float | None = None  # Optional step size override


@router.post("/api/network-camera/ptz/move")
async def ptz_move(
    request: PTZMoveRequest,
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
) -> dict[str, Any]:
    """Move the camera using PTZ controls - requires authentication.

    Direction can be: up, down, left, right, zoomin, zoomout
    """
    device = _get_network_camera_device(context)
    if not device:
        return {"success": False, "message": "Network camera not configured"}

    # Validate direction
    valid_directions = {"up", "down", "left", "right", "zoomin", "zoomout"}
    if request.direction not in valid_directions:
        return {
            "success": False,
            "message": f"Invalid direction. Must be one of: {', '.join(valid_directions)}",
        }

    try:
        success = await device.ptz_move(request.direction, request.step)
        return {
            "success": success,
            "message": "Move executed" if success else "Move failed",
            "direction": request.direction,
        }
    except Exception as e:
        logger.error("PTZ move failed", direction=request.direction, error=str(e))
        return {"success": False, "message": str(e)}
