"""Redis command listener for orchestrator commands."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sense_common.models import Command, CommandResponse
from sense_common.redis_client import publish_command, publish_response, subscribe_commands

import redis.asyncio as aioredis
from orchestrator.runner import DockerRunner

logger = logging.getLogger(__name__)


class CommandListener:
    """Listens for commands on cmd:orchestrator and dispatches them."""

    def __init__(self, redis: aioredis.Redis, runner: DockerRunner) -> None:
        self.redis = redis
        self.runner = runner
        self._shutdown = asyncio.Event()

    async def run(self) -> None:
        """Main command listener loop."""
        logger.info("Command listener started")
        try:
            async for command in subscribe_commands(self.redis, "orchestrator"):
                if self._shutdown.is_set():
                    break
                asyncio.create_task(
                    self._handle_command(command),
                    name=f"cmd-{command.action}-{command.request_id[:8]}",
                )
        except asyncio.CancelledError:
            logger.info("Command listener cancelled")
        finally:
            logger.info("Command listener stopped")

    async def _handle_command(self, command: Command) -> None:
        """Dispatch a single command to the appropriate handler."""
        handlers: dict[str, Any] = {
            "start_camera": self._handle_start_camera,
            "stop_camera": self._handle_stop_camera,
            "trigger": self._handle_trigger,
            "scan_aranet4": self._handle_scan_aranet4,
            "discover_cameras": self._handle_discover_cameras,
            "restart_service": self._handle_restart_service,
        }

        handler = handlers.get(command.action)
        if handler is None:
            logger.warning("Unknown command action: %s", command.action)
            response = CommandResponse(
                request_id=command.request_id,
                status="error",
                error=f"Unknown action: {command.action}",
            )
        else:
            try:
                response = await handler(command)
            except Exception as e:
                logger.exception("Error handling command %s", command.action)
                response = CommandResponse(
                    request_id=command.request_id,
                    status="error",
                    error=str(e),
                )

        await publish_response(self.redis, "orchestrator", response)

    async def _handle_start_camera(self, command: Command) -> CommandResponse:
        """Start camera container."""
        success = await self.runner.start_service("source-camera")
        if success:
            return CommandResponse(request_id=command.request_id, status="ok")
        return CommandResponse(
            request_id=command.request_id,
            status="error",
            error="Failed to start camera service",
        )

    async def _handle_stop_camera(self, command: Command) -> CommandResponse:
        """Send stop command to camera (it self-terminates)."""
        stop_cmd = Command(action="stop")
        await publish_command(self.redis, "network_camera", stop_cmd)
        return CommandResponse(request_id=command.request_id, status="ok")

    async def _handle_trigger(self, command: Command) -> CommandResponse:
        """Trigger an ephemeral service immediately."""
        service = command.params.get("service")
        if not service:
            return CommandResponse(
                request_id=command.request_id,
                status="error",
                error="Missing 'service' parameter",
            )
        success = await self.runner.run_ephemeral(service)
        if success:
            return CommandResponse(request_id=command.request_id, status="ok")
        return CommandResponse(
            request_id=command.request_id,
            status="error",
            error=f"Failed to run {service}",
        )

    async def _handle_scan_aranet4(self, command: Command) -> CommandResponse:
        """Run aranet4 in scan mode and return discovered devices."""
        success = await self.runner.run_ephemeral("source-aranet4", env={"MODE": "scan"})
        if not success:
            return CommandResponse(
                request_id=command.request_id,
                status="error",
                error="Aranet4 scan failed",
            )

        raw = await self.redis.get("scan:co2")
        devices: list[dict[str, Any]] = []
        if raw:
            try:
                devices = json.loads(raw)
            except json.JSONDecodeError:
                logger.error("Failed to parse scan:co2 data: %s", raw)

        return CommandResponse(
            request_id=command.request_id,
            status="ok",
            data={"devices": devices},
        )

    async def _handle_discover_cameras(self, command: Command) -> CommandResponse:
        """Run camera in discover mode and return found cameras."""
        success = await self.runner.run_ephemeral("source-camera", env={"MODE": "discover"})
        if not success:
            return CommandResponse(
                request_id=command.request_id,
                status="error",
                error="Camera discovery failed",
            )

        raw = await self.redis.get("scan:network_camera")
        cameras: list[dict[str, Any]] = []
        if raw:
            try:
                cameras = json.loads(raw)
            except json.JSONDecodeError:
                logger.error("Failed to parse scan:network_camera data: %s", raw)

        return CommandResponse(
            request_id=command.request_id,
            status="ok",
            data={"cameras": cameras},
        )

    async def _handle_restart_service(self, command: Command) -> CommandResponse:
        """Restart a service by stopping and starting it."""
        service = command.params.get("service")
        if not service:
            return CommandResponse(
                request_id=command.request_id,
                status="error",
                error="Missing 'service' parameter",
            )

        await self.runner.stop_service(service)
        success = await self.runner.start_service(service)
        if success:
            return CommandResponse(request_id=command.request_id, status="ok")
        return CommandResponse(
            request_id=command.request_id,
            status="error",
            error=f"Failed to restart {service}",
        )

    def stop(self) -> None:
        """Signal the listener to stop."""
        self._shutdown.set()
