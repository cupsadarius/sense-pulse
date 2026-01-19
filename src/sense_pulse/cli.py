"""Command-line interface for sense-pulse"""

import argparse
import asyncio
import contextlib
import logging
import signal
import sys

from sense_pulse import __version__


def setup_logging(level: str, log_file: str | None) -> None:
    """Configure logging handlers including WebSocket handler for log streaming"""
    log_level = getattr(logging, level.upper(), logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler()]

    # Add file handler if log file is specified and writable
    if log_file:
        try:
            handlers.append(logging.FileHandler(log_file))
        except PermissionError:
            print(
                f"Warning: Cannot write to {log_file}, logging to stdout only",
                file=sys.stderr,
            )

    # Add WebSocket log handler for streaming logs to web UI
    # This must be initialized early to capture all startup logs
    from sense_pulse.web.log_handler import StructuredFormatter, setup_websocket_logging

    ws_handler = setup_websocket_logging()
    handlers.append(ws_handler)

    # Use StructuredFormatter to render extra kwargs in console/file output
    formatter = StructuredFormatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    for handler in handlers:
        handler.setFormatter(formatter)

    logging.basicConfig(
        level=log_level,
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
        BabyMonitorDataSource,
        PiHoleDataSource,
        SenseHatDataSource,
        SystemStatsDataSource,
        TailscaleDataSource,
        WeatherDataSource,
    )
    from sense_pulse.devices.aranet4 import Aranet4Device
    from sense_pulse.devices.baby_monitor import BabyMonitorDevice

    # Determine config path
    config_path = Path(args.config) if args.config else find_config_file()

    # Load configuration
    config = load_config(str(config_path) if config_path else None)

    # Setup logging (override with verbose flag if set)
    log_level = "DEBUG" if args.verbose else config.logging.level
    setup_logging(log_level, config.logging.file)

    from sense_pulse.web.log_handler import get_structured_logger

    logger = get_structured_logger(__name__, component="cli")
    logger.info(
        "Starting sense-pulse",
        version=__version__,
        config_path=str(config_path) if config_path else None,
        log_level=log_level,
    )

    # =========================================================================
    # Create AppContext - single source of truth for all dependencies
    # =========================================================================
    logger.info(
        "Creating AppContext",
        cache_ttl=config.cache.ttl,
        poll_interval=config.cache.poll_interval,
    )
    context = AppContext.create(
        config=config,
        config_path=config_path,
        cache_ttl=config.cache.ttl,
        poll_interval=config.cache.poll_interval,
    )

    # Create shared hardware instances
    aranet4_device = Aranet4Device()
    context.aranet4_device = aranet4_device

    # Create baby monitor device if enabled
    baby_monitor_device: BabyMonitorDevice | None = None
    if config.baby_monitor.enabled:
        logger.info("Initializing baby monitor device")
        baby_monitor_device = BabyMonitorDevice(config.baby_monitor)
        context.baby_monitor_device = baby_monitor_device

    # Add all data sources to context
    context.add_data_source(TailscaleDataSource(config.tailscale))
    context.add_data_source(PiHoleDataSource(config.pihole))
    context.add_data_source(SystemStatsDataSource())
    context.add_data_source(SenseHatDataSource())
    context.add_data_source(Aranet4DataSource(config.aranet4, aranet4_device))
    context.add_data_source(WeatherDataSource(config.weather))

    # Add baby monitor data source if enabled
    if baby_monitor_device:
        context.add_data_source(BabyMonitorDataSource(config.baby_monitor, baby_monitor_device))

    # Start context (initializes sources, registers with cache, starts polling)
    await context.start()

    # Start baby monitor stream if enabled (don't auto-start, let user control via UI)
    # The stream will be started when user clicks play on the status page

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
    main_task: asyncio.Task | None = None

    def signal_handler(sig: signal.Signals) -> None:
        logger.info("Received shutdown signal", signal=sig.name)
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

            logger.info("Starting web server", host=args.web_host, port=args.web_port)
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

            logger.info("Starting web server", host=args.web_host, port=args.web_port)
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

        # Stop baby monitor device if running
        if baby_monitor_device:
            await baby_monitor_device.stop_stream()

        await context.shutdown()
        logger.info("Cleanup complete")


def main() -> int:
    """Main entry point - wraps async_main()"""
    return asyncio.run(async_main())


if __name__ == "__main__":
    sys.exit(main())
