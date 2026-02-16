"""Command handler for Sense HAT service."""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

from sense_common.models import Command, CommandResponse
from sense_common.redis_client import publish_response, subscribe_commands
from sensehat.display import SenseHatDisplay

logger = logging.getLogger(__name__)


class CommandHandler:
    """Handles commands received via Redis pub/sub on cmd:sensors."""

    def __init__(self, display: SenseHatDisplay):
        self.display = display

    async def handle(self, command: Command) -> CommandResponse:
        """Process a single command and return a response."""
        action = command.action

        if action == "clear":
            await self.display.clear()
            return CommandResponse(
                request_id=command.request_id, status="ok", data={"message": "Display cleared"}
            )

        if action == "set_rotation":
            rotation = command.params.get("rotation", 0)
            if rotation not in (0, 90, 180, 270):
                return CommandResponse(
                    request_id=command.request_id,
                    status="error",
                    error=f"Invalid rotation: {rotation}. Must be 0, 90, 180, or 270.",
                )
            self.display.set_rotation(rotation)
            return CommandResponse(
                request_id=command.request_id, status="ok", data={"rotation": rotation}
            )

        if action == "get_matrix":
            pixels = self.display.get_pixels()
            return CommandResponse(
                request_id=command.request_id,
                status="ok",
                data={
                    "pixels": pixels,
                    "mode": self.display.current_mode,
                    "rotation": self.display.rotation,
                },
            )

        return CommandResponse(
            request_id=command.request_id,
            status="error",
            error=f"Unknown action: {action}",
        )

    async def listen(self, redis: aioredis.Redis, shutdown_event) -> None:
        """Listen for commands on cmd:sensors and respond."""
        while not shutdown_event.is_set():
            try:
                async for cmd in subscribe_commands(redis, "sensors"):
                    if shutdown_event.is_set():
                        break
                    try:
                        response = await self.handle(cmd)
                        await publish_response(redis, "sensors", response)
                    except Exception:
                        logger.exception("Error handling command %s", cmd.action)
                        await publish_response(
                            redis,
                            "sensors",
                            CommandResponse(
                                request_id=cmd.request_id, status="error", error="Internal error"
                            ),
                        )
            except Exception:
                if not shutdown_event.is_set():
                    logger.exception("Command listener error, reconnecting...")
                    import asyncio

                    await asyncio.sleep(1)
