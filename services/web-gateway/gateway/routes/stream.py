"""HLS stream serving endpoint: GET /api/stream/{path:path}."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from gateway.deps import Auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stream", tags=["stream"])

# HLS output directory (shared volume)
HLS_DIR = Path("/hls")


@router.get("/{path:path}")
async def serve_stream_file(path: str, _user: Auth) -> FileResponse:
    """Serve HLS files (playlist + segments) from the shared volume."""
    # Sanitize path: only use the filename to prevent directory traversal
    safe_name = Path(path).name
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid path")

    file_path = HLS_DIR / safe_name

    # Playlist file
    if safe_name.endswith(".m3u8"):
        if not file_path.exists():
            raise HTTPException(status_code=503, detail="Stream not available")
        return FileResponse(
            file_path,
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    # Segment files
    if safe_name.endswith(".ts"):
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Segment not found")
        return FileResponse(file_path, media_type="video/mp2t")

    raise HTTPException(status_code=400, detail="Unsupported file type")
