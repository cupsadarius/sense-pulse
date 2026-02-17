"""FastAPI dependencies for the web gateway."""

from __future__ import annotations

import logging
import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sense_common.redis_client import read_config

import redis.asyncio as aioredis
from gateway.auth import authenticate

logger = logging.getLogger(__name__)

# HTTP Basic Auth handler
security = HTTPBasic(auto_error=False)


async def get_redis(request: Request) -> aioredis.Redis:
    """Get Redis connection from app state."""
    return request.app.state.redis


async def require_auth(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> str:
    """Require HTTP Basic Auth. Returns username.

    Auth config is read from Redis (config:auth) with env var fallback.
    If auth is disabled, returns 'anonymous'.
    """
    redis: aioredis.Redis = request.app.state.redis

    # Read auth config from Redis, fallback to env vars
    auth_config = await read_config(redis, "auth")

    if auth_config is None:
        # Build from env vars
        enabled = os.environ.get("AUTH_ENABLED", "true").lower() in ("true", "1", "yes")
        auth_config = {
            "enabled": enabled,
            "username": os.environ.get("AUTH_USERNAME", ""),
            "password_hash": os.environ.get("AUTH_PASSWORD_HASH", ""),
        }

    # If auth disabled, allow all
    if not auth_config.get("enabled", False):
        return "anonymous"

    # Auth is enabled — credentials are required
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    if not authenticate(credentials.username, credentials.password, auth_config):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username


# Type aliases for use in route signatures
Redis = Annotated[aioredis.Redis, Depends(get_redis)]
Auth = Annotated[str, Depends(require_auth)]
