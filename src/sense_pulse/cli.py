"""Command-line interface for sense-pulse"""

import argparse
import logging
import sys
import threading
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


def main() -> int:
    """Main entry point"""
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
    from sense_pulse.cache import initialize_cache
    from sense_pulse.config import load_config

    # Load configuration
    config = load_config(args.config)

    # Setup logging (override with verbose flag if set)
    log_level = "DEBUG" if args.verbose else config.logging.level
    setup_logging(log_level, config.logging.file)

    logger = logging.getLogger(__name__)
    logger.info("=" * 50)
    logger.info("Starting sense-pulse")
    logger.info("=" * 50)

    # Initialize data cache with 60s TTL and 30s polling interval
    logger.info("Initializing data cache (60s TTL, 30s poll interval)")
    cache = initialize_cache(cache_ttl=60.0, poll_interval=30.0)
    cache.start_polling()

    try:
        # Web server only mode
        if args.web_only:
            import uvicorn

            from sense_pulse.web.app import create_app

            logger.info(f"Starting web server on {args.web_host}:{args.web_port}")
            app = create_app()
            uvicorn.run(app, host=args.web_host, port=args.web_port, log_level=log_level.lower())
            return 0

        # Start web server in background thread (unless disabled)
        if not args.no_web:
            logger.info(f"Starting web server on {args.web_host}:{args.web_port}")
            web_thread = threading.Thread(
                target=run_web_server,
                args=(args.web_host, args.web_port, log_level),
                daemon=True,
            )
            web_thread.start()

        # LED display mode (requires Sense HAT)
        from sense_pulse.controller import StatsDisplay

        controller = StatsDisplay(config)

        if args.once:
            controller.run_cycle()
        else:
            controller.run_continuous()

        return 0

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 0
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
