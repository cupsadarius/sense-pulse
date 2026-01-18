"""API routes for baby monitor streaming."""

import asyncio
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse

from sense_pulse.baby_monitor import StreamManager
from sense_pulse.context import AppContext
from sense_pulse.web.app import get_context
from sense_pulse.web.auth import require_auth
from sense_pulse.web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="baby_monitor_routes")

router = APIRouter(prefix="/baby-monitor", tags=["baby-monitor"])


def _get_stream_manager(context: AppContext) -> Optional[StreamManager]:
    """Get the stream manager from context."""
    return getattr(context, "baby_monitor_stream", None)


@router.get("/", response_class=HTMLResponse)
async def baby_monitor_page(
    request: Request,
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
):
    """Render baby monitor viewer page (requires authentication)."""
    templates = request.app.state.templates
    config = context.config

    stream_manager = _get_stream_manager(context)
    stream_status = stream_manager.get_status() if stream_manager else None

    return templates.TemplateResponse(
        "baby_monitor.html",
        {
            "request": request,
            "config": config,
            "stream_status": stream_status,
            "enabled": config.baby_monitor.enabled,
        },
    )


@router.get("/api/status")
async def get_stream_status(
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
) -> dict[str, Any]:
    """Get current stream status - requires authentication."""
    stream_manager = _get_stream_manager(context)
    if not stream_manager:
        return {
            "status": "disabled",
            "enabled": False,
            "error": "Baby monitor not configured",
        }
    return stream_manager.get_status()


@router.post("/api/restart")
async def restart_stream(
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
) -> dict[str, Any]:
    """Restart the stream - requires authentication."""
    stream_manager = _get_stream_manager(context)
    if not stream_manager:
        return {"success": False, "message": "Baby monitor not configured"}

    try:
        await stream_manager.restart()
        return {"success": True, "message": "Stream restarting"}
    except Exception as e:
        logger.error("Failed to restart stream", error=str(e))
        return {"success": False, "message": str(e)}


@router.get("/stream/stream.m3u8")
async def get_hls_playlist(
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
):
    """Serve HLS playlist - requires authentication."""
    stream_manager = _get_stream_manager(context)
    if not stream_manager:
        return {"error": "Baby monitor not configured"}

    playlist_path = stream_manager.playlist_path
    if not playlist_path.exists():
        return {"error": "Stream not ready"}

    return FileResponse(
        playlist_path,
        media_type="application/vnd.apple.mpegurl",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/stream/{segment_name}")
async def get_hls_segment(
    segment_name: str,
    context: AppContext = Depends(get_context),
    username: str = Depends(require_auth),
):
    """Serve HLS segment - requires authentication."""
    stream_manager = _get_stream_manager(context)
    if not stream_manager:
        return {"error": "Baby monitor not configured"}

    # Validate segment name (must be .ts file)
    if not segment_name.endswith(".ts"):
        return {"error": "Invalid segment"}

    # Sanitize path to prevent directory traversal
    segment_path = stream_manager.output_dir / Path(segment_name).name
    if not segment_path.exists():
        return {"error": "Segment not found"}

    return FileResponse(
        segment_path,
        media_type="video/mp2t",
        headers={
            "Cache-Control": "max-age=3600",
        },
    )


@router.websocket("/ws/status")
async def stream_status_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time stream status updates."""
    await websocket.accept()

    context: AppContext = websocket.app.state.context
    stream_manager = _get_stream_manager(context)

    if not stream_manager:
        await websocket.send_json({"error": "Baby monitor not configured"})
        await websocket.close()
        return

    try:
        while True:
            status = stream_manager.get_status()
            await websocket.send_json(status)
            await asyncio.sleep(2)  # Update every 2 seconds
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
