"""Config endpoints: GET /api/config, POST /api/config."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from sense_common.redis_client import publish_config_changed, read_config, write_config

from gateway.deps import Auth, Redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])

# All known config sections
CONFIG_SECTIONS = [
    "display",
    "sleep",
    "schedule",
    "weather",
    "pihole",
    "aranet4",
    "camera",
    "auth",
]


@router.get("")
async def get_config(redis: Redis, _user: Auth) -> dict[str, Any]:
    """Return all config sections from Redis."""
    result: dict[str, Any] = {}
    for section in CONFIG_SECTIONS:
        data = await read_config(redis, section)
        if data is not None:
            # Strip password_hash from auth section for security
            if section == "auth":
                data = {k: v for k, v in data.items() if k != "password_hash"}
            result[section] = data
    return result


@router.post("")
async def update_config(request: Request, redis: Redis, _user: Auth) -> dict[str, Any]:
    """Partial config update. Write changed sections and publish notifications."""
    body = await request.json()
    sections_updated: list[str] = []

    for section, data in body.items():
        if section not in CONFIG_SECTIONS:
            continue
        if not isinstance(data, dict):
            continue

        # Merge with existing config (partial update)
        existing = await read_config(redis, section) or {}
        existing.update(data)

        await write_config(redis, section, existing)
        await publish_config_changed(redis, section)
        sections_updated.append(section)

    return {"status": "ok", "sections_updated": sections_updated}
