"""Entry point for the network camera source service.

Supports two modes via MODE env var:
- MODE=stream (default): Demand-started, runs HLS stream, handles commands, self-terminates.
- MODE=discover: Scan network for RTSP cameras, write to Redis, exit.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
import time

from sense_common.config import get_config_value, get_env, get_redis_url
from sense_common.models import (
    Command,
    CommandResponse,
    SensorReading,
    SourceMetadata,
    SourceStatus,
)
from sense_common.redis_client import (
    create_redis,
    publish_data,
    publish_response,
    read_config,
    subscribe_commands,
    write_metadata,
    write_readings,
    write_status,
)

from camera.discovery import discover_cameras
from camera.ptz import PTZController
from camera.stream import StreamManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

SOURCE_ID = "network_camera"
SCAN_KEY = "scan:network_camera"
SCAN_TTL = 60  # seconds
STATUS_INTERVAL = 5  # seconds between status writes


async def run_discover_mode() -> None:
    """Scan network for RTSP cameras and write results to Redis."""
    redis_url = get_redis_url()
    redis = await create_redis(redis_url)

    try:
        config = await read_config(redis, "camera")
        timeout: int = get_config_value(config, "CAMERA_TIMEOUT", default=30, config_key="timeout")

        cameras = await discover_cameras(timeout=timeout)

        await redis.set(SCAN_KEY, json.dumps(cameras), ex=SCAN_TTL)
        logger.info("Discover mode: wrote %d cameras to %s", len(cameras), SCAN_KEY)
    finally:
        await redis.aclose()


async def run_stream_mode() -> None:
    """Run the HLS stream service with command handling and self-termination."""
    redis_url = get_redis_url()
    redis = await create_redis(redis_url)
    shutdown_event = asyncio.Event()

    # Install signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_event.set)

    try:
        # Read camera config
        config = await read_config(redis, "camera")
        cameras_config: list[dict] = get_config_value(
            config, "CAMERA_CONFIG", default=[], config_key="cameras"
        )
        output_dir: str = get_config_value(
            config, "HLS_OUTPUT_DIR", default="/hls", config_key="output_dir"
        )

        if not cameras_config:
            logger.error("No cameras configured")
            return

        cam = cameras_config[0]
        rtsp_url = _build_rtsp_url(cam)

        if not rtsp_url:
            logger.error("Could not build RTSP URL from camera config")
            return

        # Create stream manager
        stream_manager = StreamManager(
            rtsp_url=rtsp_url,
            output_dir=output_dir,
            transport=cam.get("transport", "tcp"),
        )

        # Create PTZ controller if enabled
        ptz_controller: PTZController | None = None
        if cam.get("ptz_enabled", False):
            ptz_controller = PTZController(
                ptz_step=cam.get("ptz_step", 0.05),
                ptz_zoom_step=cam.get("ptz_zoom_step", 0.1),
            )
            await ptz_controller.initialize(
                host=cam.get("host", ""),
                port=cam.get("onvif_port", 8000),
                username=cam.get("username", ""),
                password=cam.get("password", ""),
                wsdl_dir=cam.get("onvif_wsdl_dir", ""),
            )

        # Write metadata
        await write_metadata(
            redis,
            SOURCE_ID,
            SourceMetadata(
                source_id=SOURCE_ID,
                name="Network Camera",
                description="RTSP network camera HLS stream",
                refresh_interval=5,
            ),
        )

        # Start stream immediately
        started = await stream_manager.start()
        if not started:
            logger.error("Failed to start stream")
            # Write error status
            await _write_stream_readings(redis, stream_manager)
            return

        # Run concurrent tasks
        await asyncio.gather(
            _command_listener(redis, stream_manager, ptz_controller, shutdown_event),
            _status_writer(redis, stream_manager, shutdown_event),
            _wait_for_shutdown(shutdown_event),
            return_exceptions=True,
        )

    finally:
        if ptz_controller:
            await ptz_controller.shutdown()
        await redis.aclose()


async def _command_listener(
    redis: object,
    stream_manager: StreamManager,
    ptz_controller: PTZController | None,
    shutdown_event: asyncio.Event,
) -> None:
    """Listen for commands on cmd:network_camera."""
    while not shutdown_event.is_set():
        try:
            async for command in subscribe_commands(redis, SOURCE_ID):  # type: ignore[arg-type]
                if shutdown_event.is_set():
                    break

                response = await _handle_command(
                    command,
                    stream_manager,
                    ptz_controller,
                    redis,
                    shutdown_event,  # type: ignore[arg-type]
                )
                await publish_response(redis, SOURCE_ID, response)  # type: ignore[arg-type]

                if command.action == "stop":
                    # Self-terminate after stop
                    return
        except Exception:
            if not shutdown_event.is_set():
                logger.exception("Command listener error, reconnecting...")
                await asyncio.sleep(1)


async def _handle_command(
    command: Command,
    stream_manager: StreamManager,
    ptz_controller: PTZController | None,
    redis: object,
    shutdown_event: asyncio.Event,
) -> CommandResponse:
    """Handle a single command."""
    action = command.action
    logger.info("Handling command: action=%s request_id=%s", action, command.request_id)

    try:
        if action == "start":
            success = await stream_manager.start()
            return CommandResponse(
                request_id=command.request_id,
                status="ok" if success else "error",
                data=stream_manager.get_status(),
                error=None if success else "Failed to start stream",
            )

        elif action == "stop":
            await stream_manager.stop()
            # Publish stream:ended event
            ended_payload = json.dumps(
                {
                    "source_id": SOURCE_ID,
                    "reason": "user_stopped",
                    "timestamp": time.time(),
                }
            )
            await redis.publish("stream:ended", ended_payload)  # type: ignore[union-attr]
            logger.info("Published stream:ended, self-terminating")
            shutdown_event.set()
            return CommandResponse(
                request_id=command.request_id,
                status="ok",
                data={"message": "Stream stopped, container exiting"},
            )

        elif action == "restart":
            success = await stream_manager.restart()
            return CommandResponse(
                request_id=command.request_id,
                status="ok" if success else "error",
                data=stream_manager.get_status(),
                error=None if success else "Failed to restart stream",
            )

        elif action == "ptz_move":
            if ptz_controller is None:
                return CommandResponse(
                    request_id=command.request_id,
                    status="error",
                    error="PTZ not enabled",
                )
            direction = command.params.get("direction", "")
            step = command.params.get("step")
            success = await ptz_controller.move(direction, step)
            return CommandResponse(
                request_id=command.request_id,
                status="ok" if success else "error",
                error=None if success else f"PTZ move failed: {direction}",
            )

        else:
            return CommandResponse(
                request_id=command.request_id,
                status="error",
                error=f"Unknown action: {action}",
            )

    except Exception as e:
        logger.exception("Command handling error: %s", e)
        return CommandResponse(
            request_id=command.request_id,
            status="error",
            error=str(e),
        )


async def _status_writer(
    redis: object,
    stream_manager: StreamManager,
    shutdown_event: asyncio.Event,
) -> None:
    """Write 6 scalar readings to Redis every 5 seconds while streaming."""
    poll_count = 0
    while not shutdown_event.is_set():
        try:
            await _write_stream_readings(redis, stream_manager)  # type: ignore[arg-type]
            poll_count += 1
            await write_status(
                redis,  # type: ignore[arg-type]
                SOURCE_ID,
                SourceStatus(
                    source_id=SOURCE_ID,
                    last_poll=time.time(),
                    last_success=time.time(),
                    poll_count=poll_count,
                ),
            )
            await publish_data(redis, SOURCE_ID)  # type: ignore[arg-type]
        except Exception:
            logger.exception("Status writer error")

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=STATUS_INTERVAL)
            break
        except TimeoutError:
            pass


async def _write_stream_readings(redis: object, stream_manager: StreamManager) -> None:
    """Write 6 scalar readings per CONTRACT.md."""
    status = stream_manager.get_status()
    readings = [
        SensorReading(
            sensor_id="stream_status",
            value=status["status"],
            unit=None,
        ),
        SensorReading(
            sensor_id="stream_connected",
            value=status["connected"],
            unit=None,
        ),
        SensorReading(
            sensor_id="stream_error",
            value=status["error"] or "",
            unit=None,
        ),
        SensorReading(
            sensor_id="stream_resolution",
            value=status["resolution"] or "",
            unit=None,
        ),
        SensorReading(
            sensor_id="stream_fps",
            value=status["fps"] or 0,
            unit="fps",
        ),
        SensorReading(
            sensor_id="stream_uptime",
            value=round(status["uptime"], 1),
            unit="seconds",
        ),
    ]
    await write_readings(redis, SOURCE_ID, readings)  # type: ignore[arg-type]


async def _wait_for_shutdown(shutdown_event: asyncio.Event) -> None:
    """Wait for shutdown signal, then exit."""
    await shutdown_event.wait()
    logger.info("Shutdown signal received, exiting")
    # Give other tasks time to finish
    await asyncio.sleep(1)
    sys.exit(0)


def _build_rtsp_url(cam: dict) -> str:
    """Build RTSP URL from camera config dict."""
    host = cam.get("host", "")
    if not host:
        return ""

    port = cam.get("port", 554)
    username = cam.get("username", "")
    password = cam.get("password", "")
    stream_path = cam.get("stream_path", "/Streaming/Channels/101").lstrip("/")

    auth = f"{username}:{password}@" if username else ""
    return f"rtsp://{auth}{host}:{port}/{stream_path}"


def main() -> None:
    mode = get_env("MODE", "stream").lower()
    logger.info("Camera service starting in %s mode", mode)

    if mode == "discover":
        asyncio.run(run_discover_mode())
    else:
        asyncio.run(run_stream_mode())


if __name__ == "__main__":
    main()
