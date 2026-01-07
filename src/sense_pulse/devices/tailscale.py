"""Tailscale connection status monitoring"""

import asyncio
import json
import time
from typing import Any, Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="tailscale")


class TailscaleStatus:
    """Handles checking Tailscale connection status"""

    def __init__(self, cache_duration: int = 30):
        """
        Initialize Tailscale status checker.

        Args:
            cache_duration: Seconds to cache status data
        """
        self._cached_data: Optional[dict] = None
        self._last_fetch: float = 0
        self._cache_duration = cache_duration
        logger.info("Initialized Tailscale status checker", cache_duration=cache_duration)

    @retry(
        retry=retry_if_exception_type(asyncio.TimeoutError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _fetch_status(self) -> Optional[dict]:
        """Fetch Tailscale status data with caching (with retries)"""
        current_time = time.time()

        # Return cached data if still valid
        if self._cached_data and (current_time - self._last_fetch) < self._cache_duration:
            logger.debug("Using cached Tailscale status")
            return self._cached_data

        try:
            logger.debug("Fetching fresh Tailscale status...")
            process = await asyncio.create_subprocess_exec(
                "tailscale",
                "status",
                "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)

            if process.returncode == 0:
                data = json.loads(stdout.decode())
                self._cached_data = data
                self._last_fetch = current_time
                logger.debug("Successfully fetched Tailscale status")
                return data
            else:
                logger.debug("Tailscale command failed or not connected")
                return None

        except asyncio.TimeoutError as e:
            logger.warning("Tailscale status check timed out (will retry)", error=str(e))
            raise
        except FileNotFoundError:
            logger.error("Tailscale command not found - is it installed?")
            return None
        except json.JSONDecodeError as e:
            logger.error("Failed to parse Tailscale JSON output", error=str(e))
            return None
        except Exception as e:
            logger.error("Error checking Tailscale status", error=str(e))
            return None

    async def is_connected(self) -> bool:
        """Check if Tailscale is connected"""
        status = await self._fetch_status()
        if not status:
            return False
        return status.get("Self") is not None and status.get("BackendState") == "Running"

    async def get_connected_device_count(self) -> int:
        """Get count of connected Tailscale devices (peers)"""
        status = await self._fetch_status()
        if not status:
            logger.debug("No Tailscale status data, returning 0 devices")
            return 0

        peers = status.get("Peer", {})
        online_count = sum(1 for peer in peers.values() if peer.get("Online", False))

        logger.debug("Tailscale device count", online=online_count, total_peers=len(peers))
        return online_count

    async def get_status_summary(self) -> dict[str, Any]:
        """Get comprehensive Tailscale status summary"""
        return {
            "connected": await self.is_connected(),
            "device_count": await self.get_connected_device_count(),
        }
