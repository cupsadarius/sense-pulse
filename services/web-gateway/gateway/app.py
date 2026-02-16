"""FastAPI application factory for the Sense Pulse web gateway."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sense_common.config import get_redis_url
from sense_common.redis_client import create_redis

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Connect Redis on startup, close on shutdown."""
    redis_url = get_redis_url()
    logger.info("Connecting to Redis at %s", redis_url)
    redis = await create_redis(redis_url)
    app.state.redis = redis

    yield

    logger.info("Closing Redis connection")
    await redis.aclose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Sense Pulse Gateway",
        description="JSON API gateway for Sense Pulse",
        version="0.12.0",
        lifespan=lifespan,
    )

    # CORS middleware
    origins_str = os.environ.get("CORS_ORIGINS", "")
    origins = [o.strip() for o in origins_str.split(",") if o.strip()] if origins_str else []
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Include route modules
    from gateway.routes.command import router as command_router
    from gateway.routes.config import router as config_router
    from gateway.routes.health import router as health_router
    from gateway.routes.sources import router as sources_router
    from gateway.routes.stream import router as stream_router
    from gateway.websocket.grid import router as grid_ws_router
    from gateway.websocket.sources import router as sources_ws_router

    app.include_router(health_router)
    app.include_router(sources_router)
    app.include_router(config_router)
    app.include_router(command_router)
    app.include_router(stream_router)
    app.include_router(sources_ws_router)
    app.include_router(grid_ws_router)

    return app
