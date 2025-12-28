"""FastAPI application for Sense Pulse web interface"""

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from pathlib import Path

from sense_pulse.web.routes import router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application"""
    app = FastAPI(
        title="Sense Pulse",
        description="Pi-hole + Tailscale + Sense HAT Status Dashboard",
        version="0.4.0",
    )

    # Templates directory
    templates_dir = Path(__file__).parent / "templates"

    app.state.templates = Jinja2Templates(directory=str(templates_dir))

    # Include API routes
    app.include_router(router)

    return app
