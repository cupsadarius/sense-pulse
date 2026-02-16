"""WebSocket endpoint for real-time source data: WS /ws/sources."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from sense_common.redis_client import read_all_sources, read_all_statuses

logger = logging.getLogger(__name__)

router = APIRouter()

BATCH_INTERVAL = 5.0  # Aggregate pub/sub notifications for 5 seconds
POLL_FALLBACK = 30.0  # If no pub/sub in 30s, poll and push
HEARTBEAT_INTERVAL = 30.0  # Keep-alive ping


async def _build_snapshot(redis: Any) -> dict[str, Any]:
    """Build a full snapshot matching GET /api/sources shape."""
    all_readings = await read_all_sources(redis)
    all_statuses = await read_all_statuses(redis)
    status_by_id = {s.source_id: s for s in all_statuses}
    all_ids = set(all_readings.keys()) | set(status_by_id.keys())

    result: dict[str, Any] = {}
    for source_id in sorted(all_ids):
        status = status_by_id.get(source_id)
        result[source_id] = {
            "readings": all_readings.get(source_id, {}),
            "status": {
                "last_poll": status.last_poll,
                "last_success": status.last_success,
                "last_error": status.last_error,
                "poll_count": status.poll_count,
                "error_count": status.error_count,
            }
            if status
            else None,
        }
    return result


@router.websocket("/ws/sources")
async def sources_ws(websocket: WebSocket) -> None:
    """Real-time source data via WebSocket.

    Subscribes to all data:* channels, batches updates for 5 seconds,
    then pushes a full snapshot. Falls back to polling every 30s.
    """
    await websocket.accept()
    redis = websocket.app.state.redis

    # Send initial snapshot
    try:
        snapshot = await _build_snapshot(redis)
        await websocket.send_json(snapshot)
    except Exception:
        logger.exception("Failed to send initial snapshot")
        await websocket.close()
        return

    # Subscribe to data:* channels using a separate connection
    pubsub = redis.pubsub()
    await pubsub.psubscribe("data:*")

    try:
        last_push = asyncio.get_event_loop().time()
        pending_update = False

        while True:
            now = asyncio.get_event_loop().time()

            # Check for pub/sub messages (non-blocking batch)
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True), timeout=1.0
                )
                if message and message["type"] in ("message", "pmessage"):
                    pending_update = True
            except asyncio.TimeoutError:
                pass

            now = asyncio.get_event_loop().time()
            time_since_push = now - last_push

            # Push if we have pending updates and batch interval elapsed
            if pending_update and time_since_push >= BATCH_INTERVAL:
                snapshot = await _build_snapshot(redis)
                await websocket.send_json(snapshot)
                last_push = now
                pending_update = False

            # Fallback poll if no updates for POLL_FALLBACK seconds
            elif time_since_push >= POLL_FALLBACK:
                snapshot = await _build_snapshot(redis)
                await websocket.send_json(snapshot)
                last_push = now
                pending_update = False

            # Heartbeat
            elif time_since_push >= HEARTBEAT_INTERVAL and not pending_update:
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.debug("WebSocket /ws/sources disconnected")
    except Exception:
        logger.exception("WebSocket /ws/sources error")
    finally:
        await pubsub.punsubscribe("data:*")
        await pubsub.aclose()
