"""FastAPI application for Sense Pulse web interface."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Optional, cast

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

if TYPE_CHECKING:
    from sense_pulse.context import AppContext

from sense_pulse.web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="webapp")


def get_context(request: Request) -> "AppContext":
    """
    FastAPI dependency to get AppContext from request.

    This is the recommended way to access the AppContext in route handlers.
    Use with Depends(): `context: AppContext = Depends(get_context)`

    Args:
        request: The FastAPI request object

    Returns:
        The AppContext instance

    Raises:
        RuntimeError: If AppContext is not initialized
    """
    if not hasattr(request.app.state, "context") or request.app.state.context is None:
        raise RuntimeError("AppContext not initialized. Web app must be created with context.")
    return cast("AppContext", request.app.state.context)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifespan.

    NOTE: Data sources and cache are managed by AppContext, NOT here.
    The context is created and started by the CLI before the web app starts.
    This function only handles web-specific startup/shutdown.
    """
    logger.info("Web application starting")

    # Verify context is available and started
    context = getattr(app.state, "context", None)
    if context:
        if not context.is_started:
            logger.warning("AppContext provided but not started")
        else:
            logger.info("Using AppContext", data_sources=len(context.data_sources))
    else:
        logger.warning("No AppContext provided - running in legacy mode")

    yield  # Application runs here

    logger.info("Web application shutting down")
    # Note: Context shutdown is handled by CLI, not here


def create_app(context: Optional["AppContext"] = None) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        context: Application context with cache, config, and data sources.
                 If None, app will run without context (limited functionality).

    Returns:
        Configured FastAPI application

    Example:
        # With context (recommended)
        context = AppContext.create(config)
        await context.start()
        app = create_app(context=context)
    """
    app = FastAPI(
        title="Sense Pulse",
        description="Pi-hole + Tailscale + Sense HAT Status Dashboard",
        version="0.11.0",
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

    # Include API routes (includes network camera endpoints)
    from sense_pulse.web.routes import router

    app.include_router(router)

    if context:
        logger.info("FastAPI application created", mode="context")
    else:
        logger.info("FastAPI application created", mode="legacy")

    return app
