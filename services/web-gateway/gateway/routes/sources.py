"""Source data endpoints: GET /api/sources, GET /api/sources/{source_id}."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from sense_common.redis_client import read_all_sources, read_all_statuses, read_source, read_status

from gateway.deps import Auth, Redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sources", tags=["sources"])


def _status_to_dict(status: Any) -> dict[str, Any] | None:
    """Convert a SourceStatus model to the API response dict (without source_id)."""
    if status is None:
        return None
    return {
        "last_poll": status.last_poll,
        "last_success": status.last_success,
        "last_error": status.last_error,
        "poll_count": status.poll_count,
        "error_count": status.error_count,
    }


@router.get("")
async def get_all_sources(redis: Redis, _user: Auth) -> dict[str, Any]:
    """Return all sources: readings + status merged."""
    all_readings = await read_all_sources(redis)
    all_statuses = await read_all_statuses(redis)

    # Index statuses by source_id
    status_by_id = {s.source_id: s for s in all_statuses}

    # Collect all source IDs from both readings and statuses
    all_ids = set(all_readings.keys()) | set(status_by_id.keys())

    result: dict[str, Any] = {}
    for source_id in sorted(all_ids):
        result[source_id] = {
            "readings": all_readings.get(source_id, {}),
            "status": _status_to_dict(status_by_id.get(source_id)),
        }

    return result


@router.get("/{source_id}")
async def get_source(source_id: str, redis: Redis, _user: Auth) -> dict[str, Any]:
    """Return a single source: readings + status."""
    readings = await read_source(redis, source_id)
    status = await read_status(redis, source_id)

    if not readings and status is None:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found")

    return {
        "readings": readings,
        "status": _status_to_dict(status),
    }
