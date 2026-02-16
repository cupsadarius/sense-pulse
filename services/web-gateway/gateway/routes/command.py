"""Command dispatch endpoint: POST /api/command/{target}."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from sense_common.models import Command
from sense_common.redis_client import publish_command, wait_response

from gateway.deps import Auth, Redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/command", tags=["command"])

# Known command targets
KNOWN_TARGETS = {"sensors", "network_camera", "orchestrator"}

# Action-specific timeouts (seconds)
ACTION_TIMEOUTS: dict[str, float] = {
    "start_camera": 10.0,
    "scan_aranet4": 30.0,
    "discover_cameras": 30.0,
}

DEFAULT_TIMEOUT = 5.0


@router.post("/{target}")
async def dispatch_command(
    target: str, request: Request, redis: Redis, _user: Auth
) -> dict[str, Any]:
    """Dispatch a command to a service via Redis pub/sub and wait for response."""
    if target not in KNOWN_TARGETS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown target '{target}'. Must be one of: {', '.join(sorted(KNOWN_TARGETS))}",
        )

    body = await request.json()
    action = body.get("action")
    if not action:
        raise HTTPException(status_code=400, detail="Missing 'action' field")

    params = body.get("params", {})

    # Create and publish command
    command = Command(action=action, params=params)

    await publish_command(redis, target, command)

    # Wait for response with action-specific timeout
    timeout = ACTION_TIMEOUTS.get(action, DEFAULT_TIMEOUT)
    response = await wait_response(redis, target, command.request_id, timeout=timeout)

    if response is None:
        return {
            "success": False,
            "message": f"Timeout waiting for response from '{target}' (action: {action})",
        }

    if response.status == "error":
        return {
            "success": False,
            "message": response.error or "Command failed",
            "data": response.data if response.data else None,
        }

    return {
        "success": True,
        "message": response.data.get("message", "Command executed"),
        "data": response.data if response.data else None,
    }
