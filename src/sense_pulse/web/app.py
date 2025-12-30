"""FastAPI application for Sense Pulse web interface."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

if TYPE_CHECKING:
    from sense_pulse.context import AppContext

logger = logging.getLogger(__name__)

# Module-level reference to context (set by create_app)
# This is necessary because FastAPI's lifespan function cannot receive parameters
_app_context: Optional["AppContext"] = None


def get_app_context() -> Optional["AppContext"]:
    """
    Get the application context.

    This function provides access to the AppContext from anywhere in the web module.
    It is set when create_app() is called with a context.

    Returns:
        The AppContext if set, None otherwise (legacy mode)
    """
    return _app_context


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifespan.

    NOTE: Data sources and cache are managed by AppContext, NOT here.
    The context is created and started by the CLI before the web app starts.
    This function only handles web-specific startup/shutdown.
    """
    logger.info("Web application starting...")

    # Verify context is available and started
    if _app_context:
        if not _app_context.is_started:
            logger.warning(
                "AppContext provided but not started - " "this may indicate a configuration issue"
            )
        else:
            logger.info(f"Using AppContext with {len(_app_context.data_sources)} data source(s)")
    else:
        logger.warning("No AppContext provided - running in legacy mode with global cache")

    yield  # Application runs here

    logger.info("Web application shutting down...")
    # Note: Context shutdown is handled by CLI, not here


def create_app(context: Optional["AppContext"] = None) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        context: Application context with cache, config, and data sources.
                 If None, falls back to legacy global cache for backwards compatibility.

    Returns:
        Configured FastAPI application

    Example:
        # With context (recommended)
        context = AppContext.create(config)
        await context.start()
        app = create_app(context=context)

        # Without context (legacy, deprecated)
        app = create_app()
    """
    global _app_context
    _app_context = context

    app = FastAPI(
        title="Sense Pulse",
        description="Pi-hole + Tailscale + Sense HAT Status Dashboard",
        version="0.10.0",
        lifespan=lifespan,
    )

    # Store context in app.state for access in request handlers
    app.state.context = context

    # Templates directory
    templates_dir = Path(__file__).parent / "templates"
    app.state.templates = Jinja2Templates(directory=str(templates_dir))

    # Initialize auth and hardware settings if context is provided
    if context:
        from sense_pulse.devices import sensehat
        from sense_pulse.web.auth import AuthConfig as WebAuthConfig
        from sense_pulse.web.auth import set_auth_config

        # Set up auth
        auth_config = WebAuthConfig(
            enabled=context.config.auth.enabled,
            username=context.config.auth.username,
            password_hash=context.config.auth.password_hash,
        )
        set_auth_config(auth_config)

        # Initialize hardware settings
        sensehat.set_web_rotation_offset(context.config.display.web_rotation_offset)

    # Include API routes
    from sense_pulse.web.routes import router

    app.include_router(router)

    if context:
        logger.info("FastAPI application created with AppContext")
    else:
        logger.info("FastAPI application created in legacy mode")

    return app
