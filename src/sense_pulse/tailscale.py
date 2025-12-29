"""Tailscale connection status monitoring"""

import json
import logging
import subprocess
import time
from typing import Any, Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


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
        logger.info(f"Initialized Tailscale status checker (cache: {cache_duration}s)")

    @retry(
        retry=retry_if_exception_type(subprocess.TimeoutExpired),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _fetch_status(self) -> Optional[dict]:
        """Fetch Tailscale status data with caching (with retries)"""
        current_time = time.time()

        # Return cached data if still valid
        if self._cached_data and (current_time - self._last_fetch) < self._cache_duration:
            logger.debug("Using cached Tailscale status")
            return self._cached_data

        try:
            logger.debug("Fetching fresh Tailscale status...")
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                data = json.loads(result.stdout)
                self._cached_data = data
                self._last_fetch = current_time
                logger.debug("Successfully fetched Tailscale status")
                return data
            else:
                logger.debug("Tailscale command failed or not connected")
                return None

        except subprocess.TimeoutExpired as e:
            logger.warning(f"Tailscale status check timed out (will retry): {e}")
            raise
        except FileNotFoundError:
            logger.error("Tailscale command not found - is it installed?")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Tailscale JSON output: {e}")
            return None
        except Exception as e:
            logger.error(f"Error checking Tailscale status: {e}")
            return None

    def is_connected(self) -> bool:
        """Check if Tailscale is connected"""
        status = self._fetch_status()
        if not status:
            return False
        return status.get("Self") is not None and status.get("BackendState") == "Running"

    def get_connected_device_count(self) -> int:
        """Get count of connected Tailscale devices (peers)"""
        status = self._fetch_status()
        if not status:
            logger.debug("No Tailscale status data, returning 0 devices")
            return 0

        peers = status.get("Peer", {})
        online_count = sum(1 for peer in peers.values() if peer.get("Online", False))

        logger.debug(f"Tailscale: {online_count} devices online out of {len(peers)} total peers")
        return online_count

    def get_status_summary(self) -> dict[str, Any]:
        """Get comprehensive Tailscale status summary"""
        return {
            "connected": self.is_connected(),
            "device_count": self.get_connected_device_count(),
        }
