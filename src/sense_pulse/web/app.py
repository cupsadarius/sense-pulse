"""FastAPI application for Sense Pulse web interface"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from sense_pulse import hardware
from sense_pulse.cache import get_cache
from sense_pulse.web.routes import get_services, router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown"""
    # Startup: Initialize cache and register data sources
    pihole, tailscale, system, _ = get_services()
    cache = await get_cache()
    cache.register_source("tailscale", tailscale.get_status_summary)
    cache.register_source("pihole", pihole.get_summary)
    cache.register_source("system", system.get_stats)
    cache.register_source("sensors", hardware.get_sensor_data)
    cache.register_source("co2", hardware.get_aranet4_data)
    await cache.start_polling()

    yield  # Application runs here

    # Shutdown: Stop cache polling
    await cache.stop_polling()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application"""
    app = FastAPI(
        title="Sense Pulse",
        description="Pi-hole + Tailscale + Sense HAT Status Dashboard",
        version="0.4.0",
        lifespan=lifespan,
    )

    # Templates directory
    templates_dir = Path(__file__).parent / "templates"

    app.state.templates = Jinja2Templates(directory=str(templates_dir))

    # Include API routes
    app.include_router(router)

    return app
