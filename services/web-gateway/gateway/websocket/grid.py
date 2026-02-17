"""WebSocket endpoint for LED matrix state: WS /ws/grid."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/grid")
async def grid_ws(websocket: WebSocket) -> None:
    """Forward LED matrix state from Redis pub/sub to client.

    Subscribes to matrix:state channel and relays each message.
    """
    await websocket.accept()
    redis = websocket.app.state.redis

    pubsub = redis.pubsub()
    await pubsub.subscribe("matrix:state")

    try:
        while True:
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=1.0,
                )
                if message and message["type"] == "message":
                    data = json.loads(message["data"])
                    await websocket.send_json(data)
            except TimeoutError:
                pass

            # Periodic keep-alive ping to detect disconnected clients
            try:
                await websocket.send_bytes(b"")
            except Exception:
                break

    except WebSocketDisconnect:
        logger.debug("WebSocket /ws/grid disconnected")
    except Exception:
        logger.exception("WebSocket /ws/grid error")
    finally:
        await pubsub.unsubscribe("matrix:state")
        await pubsub.aclose()
