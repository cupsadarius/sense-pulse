"""Health check endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from gateway.deps import Redis

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check(redis: Redis) -> JSONResponse:
    """Check gateway + Redis health. No auth required."""
    try:
        await redis.ping()
        return JSONResponse({"status": "healthy"})
    except Exception:
        logger.exception("Health check failed")
        return JSONResponse({"status": "unhealthy"}, status_code=503)
