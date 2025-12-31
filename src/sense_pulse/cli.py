"""Command-line interface for sense-pulse"""

import argparse
import asyncio
import contextlib
import logging
import signal
import sys
from typing import Optional

from sense_pulse import __version__


def setup_logging(level: str, log_file: Optional[str]) -> None:
    """Configure logging handlers"""
    log_level = getattr(logging, level.upper(), logging.INFO)

    handlers = [logging.StreamHandler()]

    # Add file handler if log file is specified and writable
    if log_file:
        try:
            handlers.append(logging.FileHandler(log_file))
        except PermissionError:
            print(
                f"Warning: Cannot write to {log_file}, logging to stdout only",
                file=sys.stderr,
            )

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )


def run_web_server(host: str, port: int, log_level: str) -> None:
    """Run the web server in a background thread"""
    import uvicorn

    from sense_pulse.web.app import create_app

    app = create_app()
    # Use log_config=None to prevent uvicorn from reconfiguring logging
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level.lower(),
        log_config=None,
    )


async def async_main() -> int:
    """Async main entry point"""
    parser = argparse.ArgumentParser(
        prog="sense-pulse",
        description="Display Pi-hole stats, Tailscale status, and sensor data on Sense HAT",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        help="Path to config file (default: auto-detect)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one display cycle and exit",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--web-only",
        action="store_true",
        help="Start web server only (no LED display)",
    )
    parser.add_argument(
        "--no-web",
        action="store_true",
        help="Disable web server (LED display only)",
    )
    parser.add_argument(
        "--web-port",
        type=int,
        default=8080,
        help="Port for web server (default: 8080)",
    )
    parser.add_argument(
        "--web-host",
        type=str,
        default="0.0.0.0",
        help="Host for web server (default: 0.0.0.0)",
    )
    # Keep --web as hidden alias for --web-only for backwards compatibility
    parser.add_argument(
        "--web",
        action="store_true",
        dest="web_only",
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    # Defer hardware-dependent imports so --version and --help work without Sense HAT
    from pathlib import Path

    from sense_pulse.config import find_config_file, load_config
    from sense_pulse.context import AppContext
    from sense_pulse.datasources import (
        Aranet4DataSource,
        PiHoleDataSource,
        SenseHatDataSource,
        SystemStatsDataSource,
        TailscaleDataSource,
    )

    # Determine config path
    config_path = Path(args.config) if args.config else find_config_file()

    # Load configuration
    config = load_config(str(config_path) if config_path else None)

    # Setup logging (override with verbose flag if set)
    log_level = "DEBUG" if args.verbose else config.logging.level
    setup_logging(log_level, config.logging.file)

    logger = logging.getLogger(__name__)
    logger.info("=" * 50)
    logger.info("Starting sense-pulse")
    logger.info("=" * 50)

    # =========================================================================
    # Create AppContext - single source of truth for all dependencies
    # =========================================================================
    logger.info("Creating AppContext (TTL=60s, Poll=30s)")
    context = AppContext.create(
        config=config,
        config_path=config_path,
        cache_ttl=60.0,
        poll_interval=30.0,
    )

    # Add all data sources to context
    context.add_data_source(TailscaleDataSource(config.tailscale))
    context.add_data_source(PiHoleDataSource(config.pihole))
    context.add_data_source(SystemStatsDataSource())
    context.add_data_source(SenseHatDataSource())
    context.add_data_source(Aranet4DataSource(config.aranet4))

    # Start context (initializes sources, registers with cache, starts polling)
    await context.start()

    # Get SenseHat instance from data source if available
    sense_hat_instance = None
    for source in context.data_sources:
        if hasattr(source, "get_sense_hat_instance"):
            instance = source.get_sense_hat_instance()
            if instance:
                context.sense_hat = instance
                sense_hat_instance = instance
                logger.info("Found SenseHat instance from DataSource")
                break

    # Setup signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()
    main_task: Optional[asyncio.Task] = None

    def signal_handler(sig: signal.Signals) -> None:
        logger.info(f"Received signal {sig.name}, initiating graceful shutdown...")
        shutdown_event.set()
        # Also cancel the main task to interrupt any blocking operations
        if main_task and not main_task.done():
            main_task.cancel()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler, sig)

    try:
        # =====================================================================
        # Web server only mode
        # =====================================================================
        if args.web_only:
            import uvicorn

            from sense_pulse.web.app import create_app

            logger.info(f"Starting web server on {args.web_host}:{args.web_port}")
            app = create_app(context=context)  # Inject context

            config_uvicorn = uvicorn.Config(
                app,
                host=args.web_host,
                port=args.web_port,
                log_level=log_level.lower(),
                log_config=None,  # Prevent uvicorn from reconfiguring logging
            )
            server = uvicorn.Server(config_uvicorn)
            main_task = asyncio.create_task(server.serve())
            try:
                await main_task
            except asyncio.CancelledError:
                logger.info("Web server cancelled")
            return 0

        # =====================================================================
        # Start web server in background (unless disabled)
        # =====================================================================
        web_server_task = None
        if not args.no_web:
            import uvicorn

            from sense_pulse.web.app import create_app

            logger.info(f"Starting web server on {args.web_host}:{args.web_port}")
            app = create_app(context=context)  # Inject context

            config_uvicorn = uvicorn.Config(
                app,
                host=args.web_host,
                port=args.web_port,
                log_level=log_level.lower(),
                log_config=None,
            )
            server = uvicorn.Server(config_uvicorn)
            web_server_task = asyncio.create_task(server.serve())

        # =====================================================================
        # LED display mode (requires Sense HAT)
        # =====================================================================
        from sense_pulse.controller import StatsDisplay

        controller = StatsDisplay(
            config,
            cache=context.cache,
            sense_hat_instance=sense_hat_instance,
        )
        await controller.async_init()

        if args.once:
            await controller.run_cycle()
        else:
            # Run display loop until shutdown signal
            main_task = asyncio.create_task(controller.run_until_shutdown(shutdown_event))
            try:
                await main_task
            except asyncio.CancelledError:
                logger.info("Display loop cancelled")

        # Cancel web server if it's running
        if web_server_task:
            web_server_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await web_server_task

        return 0

    except asyncio.CancelledError:
        logger.info("Main task cancelled")
        return 0
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1
    finally:
        # =====================================================================
        # Cleanup using AppContext
        # =====================================================================
        logger.info("Shutting down...")
        await context.shutdown()
        logger.info("Cleanup complete")


def main() -> int:
    """Main entry point - wraps async_main()"""
    return asyncio.run(async_main())


if __name__ == "__main__":
    sys.exit(main())
