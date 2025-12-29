"""FastAPI application for Sense Pulse web interface"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from sense_pulse import hardware
from sense_pulse.cache import get_cache
from sense_pulse.config import load_config
from sense_pulse.datasources import (
    Aranet4DataSource,
    PiHoleDataSource,
    SenseHatDataSource,
    SystemStatsDataSource,
    TailscaleDataSource,
)
from sense_pulse.web.routes import get_services, router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown"""
    # Load configuration
    config = load_config()

    # Initialize hardware settings
    hardware.set_web_rotation_offset(config.display.web_rotation_offset)

    # Create data source instances
    data_sources = [
        PiHoleDataSource(config.pihole),
        TailscaleDataSource(config.tailscale),
        SystemStatsDataSource(),
        SenseHatDataSource(),
        Aranet4DataSource(config.aranet4),
    ]

    # Initialize all data sources
    for source in data_sources:
        try:
            await source.initialize()
        except Exception as e:
            # Log error but continue with other sources
            import logging
            logging.error(f"Error initializing data source: {e}")

    # Register data sources with cache
    cache = await get_cache()
    for source in data_sources:
        cache.register_data_source(source)

    # Start cache polling
    await cache.start_polling()

    yield  # Application runs here

    # Shutdown: Stop data sources and cache polling
    await cache.stop_polling()
    for source in data_sources:
        try:
            await source.shutdown()
        except Exception as e:
            import logging
            logging.error(f"Error shutting down data source: {e}")


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
