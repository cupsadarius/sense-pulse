"""Tailscale status data source."""

from __future__ import annotations

import asyncio
import json
import logging

import redis.asyncio as aioredis

from sense_common.ephemeral import EphemeralSource
from sense_common.models import SensorReading, SourceMetadata

logger = logging.getLogger(__name__)


class TailscaleSource(EphemeralSource):
    """Ephemeral source that checks Tailscale VPN status."""

    @property
    def source_id(self) -> str:
        return "tailscale"

    @property
    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            source_id="tailscale",
            name="Tailscale",
            description="VPN connection status and peer count",
            refresh_interval=30,
        )

    async def poll(self, redis: aioredis.Redis) -> list[SensorReading]:
        """Run `tailscale status --json` and return 2 readings."""
        try:
            process = await asyncio.create_subprocess_exec(
                "tailscale",
                "status",
                "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)
        except FileNotFoundError:
            logger.error("Tailscale CLI not found")
            return []
        except asyncio.TimeoutError:
            logger.warning("Tailscale status command timed out")
            return []
        except Exception as e:
            logger.error("Error running tailscale status: %s", e)
            return []

        if process.returncode != 0:
            logger.warning("tailscale status exited with code %d", process.returncode)
            return [
                SensorReading(sensor_id="connected", value=False, unit=None),
                SensorReading(sensor_id="device_count", value=0, unit="devices"),
            ]

        try:
            data = json.loads(stdout.decode())
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error("Failed to parse tailscale JSON: %s", e)
            return []

        connected = data.get("Self") is not None and data.get("BackendState") == "Running"

        peers = data.get("Peer", {})
        device_count = sum(1 for peer in peers.values() if peer.get("Online", False))

        return [
            SensorReading(sensor_id="connected", value=connected, unit=None),
            SensorReading(sensor_id="device_count", value=device_count, unit="devices"),
        ]
