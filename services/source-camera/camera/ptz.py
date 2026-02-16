"""ONVIF PTZ (Pan-Tilt-Zoom) controller.

Wraps blocking ONVIF calls in a ThreadPoolExecutor.
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger(__name__)

# PTZ direction mappings: (pan, tilt, zoom) multipliers
PTZ_DIRECTIONS: dict[str, tuple[float, float, float]] = {
    "up": (0.0, 1.0, 0.0),
    "down": (0.0, -1.0, 0.0),
    "left": (-1.0, 0.0, 0.0),
    "right": (1.0, 0.0, 0.0),
    "zoomin": (0.0, 0.0, 1.0),
    "zoomout": (0.0, 0.0, -1.0),
}


class PTZController:
    """ONVIF PTZ controller for network cameras.

    Uses ThreadPoolExecutor for blocking ONVIF calls.
    """

    def __init__(
        self,
        ptz_step: float = 0.05,
        ptz_zoom_step: float = 0.1,
    ) -> None:
        self._ptz_step = ptz_step
        self._ptz_zoom_step = ptz_zoom_step

        self._client: Any = None
        self._ptz_service: Any = None
        self._profile_token: str | None = None
        self._initialized = False
        self._lock = asyncio.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ptz")

    @property
    def initialized(self) -> bool:
        return self._initialized

    async def initialize(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        wsdl_dir: str = "",
    ) -> bool:
        """Initialize ONVIF PTZ connection.

        Args:
            host: Camera IP address
            port: ONVIF port (typically 8000)
            username: Camera username
            password: Camera password
            wsdl_dir: Path to ONVIF WSDL files (empty = use built-in)

        Returns:
            True if initialized successfully, False otherwise.
        """
        if self._initialized:
            return True

        async with self._lock:
            if self._initialized:
                return True

            try:
                from onvif import ONVIFCamera

                loop = asyncio.get_event_loop()

                logger.info("Initializing ONVIF PTZ: host=%s port=%d", host, port)

                def create_onvif_client() -> Any:
                    wsdl = wsdl_dir if wsdl_dir else None
                    return ONVIFCamera(host, port, username, password, wsdl)

                self._client = await loop.run_in_executor(self._executor, create_onvif_client)

                client = self._client

                def get_ptz_service() -> Any:
                    return client.create_ptz_service()

                self._ptz_service = await loop.run_in_executor(self._executor, get_ptz_service)

                def get_profiles() -> Any:
                    media_service = client.create_media_service()
                    return media_service.GetProfiles()

                profiles = await loop.run_in_executor(self._executor, get_profiles)

                if not profiles:
                    logger.error("No media profiles found on camera")
                    return False

                self._profile_token = profiles[0].token
                self._initialized = True
                logger.info("PTZ initialized: profile_token=%s", self._profile_token)
                return True

            except ImportError:
                logger.error("onvif-zeep library not installed")
                return False
            except Exception as e:
                logger.error("Failed to initialize PTZ: %s", e)
                self._client = None
                self._ptz_service = None
                self._profile_token = None
                self._initialized = False
                return False

    async def move(self, direction: str, step: float | None = None) -> bool:
        """Execute a PTZ relative move.

        Args:
            direction: One of "up", "down", "left", "right", "zoomin", "zoomout"
            step: Optional step size override

        Returns:
            True if move was executed successfully, False otherwise.
        """
        if direction not in PTZ_DIRECTIONS:
            logger.error("Invalid PTZ direction: %s", direction)
            return False

        if not self._initialized or not self._ptz_service or not self._profile_token:
            logger.error("PTZ service not available")
            return False

        pan_step = step if step is not None else self._ptz_step
        tilt_step = step if step is not None else self._ptz_step
        zoom_step = step if step is not None else self._ptz_zoom_step

        pan_dir, tilt_dir, zoom_dir = PTZ_DIRECTIONS[direction]
        pan = pan_dir * pan_step
        tilt = tilt_dir * tilt_step
        zoom = zoom_dir * zoom_step

        async with self._lock:
            try:
                loop = asyncio.get_event_loop()
                ptz_service = self._ptz_service
                profile_token = self._profile_token

                def execute_continuous_move() -> None:
                    request = ptz_service.create_type("ContinuousMove")
                    request.ProfileToken = profile_token
                    request.Velocity = {
                        "PanTilt": {"x": pan, "y": tilt},
                        "Zoom": {"x": zoom},
                    }
                    ptz_service.ContinuousMove(request)
                    time.sleep(0.3)
                    # Stop by sending zero velocity
                    request.Velocity = {
                        "PanTilt": {"x": 0, "y": 0},
                        "Zoom": {"x": 0},
                    }
                    ptz_service.ContinuousMove(request)

                await loop.run_in_executor(self._executor, execute_continuous_move)

                logger.debug(
                    "PTZ move: direction=%s pan=%.3f tilt=%.3f zoom=%.3f",
                    direction,
                    pan,
                    tilt,
                    zoom,
                )
                return True

            except Exception as e:
                logger.error("PTZ move failed: direction=%s error=%s", direction, e)
                return False

    async def shutdown(self) -> None:
        """Cleanup PTZ resources."""
        async with self._lock:
            self._client = None
            self._ptz_service = None
            self._profile_token = None
            self._initialized = False

            if self._executor:
                self._executor.shutdown(wait=False)
                self._executor = None  # type: ignore[assignment]

            logger.info("PTZ shutdown complete")
