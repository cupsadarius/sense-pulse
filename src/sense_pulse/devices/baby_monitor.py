"""Baby monitor device with ONVIF discovery and RTSP streaming.

Handles:
- ONVIF network discovery to find cameras
- FFmpeg subprocess lifecycle (start, stop, restart)
- RTSP to HLS transcoding
- Automatic reconnection with exponential backoff
- Stream health monitoring
- HLS segment cleanup
- Thumbnail capture from RTSP stream
"""

import asyncio
import contextlib
import shutil
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from sense_pulse.config import BabyMonitorConfig
from sense_pulse.web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="baby_monitor")


class StreamStatus(Enum):
    """Stream status states."""

    STOPPED = "stopped"
    STARTING = "starting"
    STREAMING = "streaming"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class CameraInfo:
    """Information about a discovered or configured camera."""

    name: str
    rtsp_url: str
    onvif_address: str | None = None
    manufacturer: str | None = None
    model: str | None = None


@dataclass
class StreamState:
    """Current state of the stream."""

    status: StreamStatus = StreamStatus.STOPPED
    start_time: float | None = None
    last_segment_time: float | None = None
    reconnect_attempts: int = 0
    error_message: str | None = None
    resolution: str | None = None
    fps: int | None = None


@dataclass
class BabyMonitorDevice:
    """
    Baby monitor device with ONVIF discovery and HLS streaming.

    This device follows the project's device architecture pattern:
    - Single instance on AppContext
    - Manages hardware/network lifecycle
    - Provides operations for discovery, streaming, thumbnails

    Attributes:
        config: Baby monitor configuration
        state: Current stream state
    """

    config: BabyMonitorConfig
    state: StreamState = field(default_factory=StreamState)
    _process: asyncio.subprocess.Process | None = None
    _monitor_task: asyncio.Task | None = None
    _shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _thumbnail_cache: bytes | None = None
    _thumbnail_timestamp: float = 0.0
    _active_camera: CameraInfo | None = None

    def __post_init__(self) -> None:
        """Initialize non-field attributes."""
        self._shutdown_event = asyncio.Event()
        self._lock = asyncio.Lock()

        # Set active camera from config if available
        if self.config.cameras:
            first_camera = self.config.cameras[0]
            self._active_camera = CameraInfo(
                name=first_camera.get("name", "default"),
                rtsp_url=first_camera.get("rtsp_url", ""),
                onvif_address=first_camera.get("onvif_address"),
            )

    @property
    def output_dir(self) -> Path:
        """Get the HLS output directory."""
        return Path(self.config.output_dir)

    @property
    def playlist_path(self) -> Path:
        """Get the HLS playlist file path."""
        return self.output_dir / "stream.m3u8"

    @property
    def thumbnail_path(self) -> Path:
        """Get the thumbnail file path."""
        return self.output_dir / "thumbnail.jpg"

    @property
    def is_streaming(self) -> bool:
        """Check if stream is currently active."""
        return self.state.status == StreamStatus.STREAMING

    @property
    def uptime_seconds(self) -> float:
        """Get stream uptime in seconds."""
        if self.state.start_time is None:
            return 0.0
        return time.time() - self.state.start_time

    @property
    def active_rtsp_url(self) -> str:
        """Get the active RTSP URL."""
        if self._active_camera:
            return self._active_camera.rtsp_url
        return ""

    def _ensure_output_dir(self) -> None:
        """Create output directory if it doesn't exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _cleanup_segments(self) -> None:
        """Remove all HLS segments and playlist."""
        if self.output_dir.exists():
            for f in self.output_dir.glob("*.ts"):
                with contextlib.suppress(OSError):
                    f.unlink()
            with contextlib.suppress(OSError):
                if self.playlist_path.exists():
                    self.playlist_path.unlink()

    def _mask_rtsp_url(self, url: str) -> str:
        """Mask credentials in RTSP URL for logging."""
        if "@" in url:
            parts = url.split("@", 1)
            protocol_and_creds = parts[0]
            host_and_path = parts[1]
            protocol = protocol_and_creds.split("://")[0]
            return f"{protocol}://***@{host_and_path}"
        return url

    def _build_ffmpeg_command(self) -> list[str]:
        """Build the FFmpeg command for RTSP to HLS transcoding."""
        rtsp_url = self.active_rtsp_url
        logger.info("Building FFmpeg command", rtsp_url=self._mask_rtsp_url(rtsp_url))

        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            # Input options
            "-rtsp_transport",
            self.config.transport,
            "-i",
            rtsp_url,
            # Video: copy H.264 (no transcode)
            "-c:v",
            "copy",
            # Audio: transcode to AAC for browser compatibility
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            # HLS output options
            "-f",
            "hls",
            "-hls_time",
            str(self.config.hls_segment_duration),
            "-hls_list_size",
            str(self.config.hls_playlist_size),
            "-hls_flags",
            "delete_segments+append_list",
            "-hls_segment_filename",
            str(self.output_dir / "segment_%03d.ts"),
            str(self.playlist_path),
        ]

    async def _read_stderr(self, stderr: asyncio.StreamReader) -> None:
        """Read and log FFmpeg stderr output."""
        import re

        while True:
            try:
                line = await stderr.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded:
                    # Parse resolution/fps from FFmpeg output if present
                    if "Video:" in decoded and "x" in decoded:
                        match = re.search(r"(\d{3,4})x(\d{3,4})", decoded)
                        if match:
                            self.state.resolution = f"{match.group(1)}x{match.group(2)}"
                        fps_match = re.search(r"(\d+(?:\.\d+)?)\s*fps", decoded)
                        if fps_match:
                            self.state.fps = int(float(fps_match.group(1)))
                    logger.debug("FFmpeg", output=decoded)
            except Exception:
                break

    async def _monitor_stream(self) -> None:
        """Monitor stream health and handle reconnection."""
        stale_threshold = 10  # Seconds before considering stream stale

        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(2)

                if self._process is None:
                    continue

                # Check if process is still running
                if self._process.returncode is not None:
                    logger.warning(
                        "FFmpeg process exited",
                        return_code=self._process.returncode,
                    )
                    self.state.status = StreamStatus.ERROR
                    self.state.error_message = f"FFmpeg exited with code {self._process.returncode}"
                    await self._handle_reconnect()
                    continue

                # Check for stale segments
                if self.playlist_path.exists():
                    mtime = self.playlist_path.stat().st_mtime
                    self.state.last_segment_time = mtime
                    age = time.time() - mtime

                    if age > stale_threshold:
                        logger.warning(
                            "Stream appears stale",
                            segment_age=age,
                            threshold=stale_threshold,
                        )
                        self.state.status = StreamStatus.ERROR
                        self.state.error_message = "Stream stale - no new segments"
                        await self._handle_reconnect()
                    elif self.state.status != StreamStatus.STREAMING:
                        # Stream recovered
                        self.state.status = StreamStatus.STREAMING
                        self.state.error_message = None
                        self.state.reconnect_attempts = 0
                        logger.info("Stream is healthy")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Monitor error", error=str(e))

    async def _handle_reconnect(self) -> None:
        """Handle stream reconnection with exponential backoff."""
        max_attempts = self.config.max_reconnect_attempts

        if max_attempts != -1 and self.state.reconnect_attempts >= max_attempts:
            logger.error(
                "Max reconnect attempts reached",
                attempts=self.state.reconnect_attempts,
            )
            self.state.status = StreamStatus.ERROR
            self.state.error_message = "Max reconnect attempts reached"
            return

        self.state.status = StreamStatus.RECONNECTING
        self.state.reconnect_attempts += 1

        # Exponential backoff: 5s, 10s, 20s, 40s... capped at 60s
        delay = min(
            self.config.reconnect_delay * (2 ** (self.state.reconnect_attempts - 1)),
            60,
        )

        logger.info(
            "Reconnecting",
            attempt=self.state.reconnect_attempts,
            delay=delay,
        )

        # Stop current process
        await self._stop_process()

        # Wait before reconnecting
        await asyncio.sleep(delay)

        if not self._shutdown_event.is_set():
            await self._start_process()

    async def _start_process(self) -> None:
        """Start the FFmpeg process."""
        async with self._lock:
            if self._process is not None:
                return

            self._ensure_output_dir()
            self._cleanup_segments()

            self.state.status = StreamStatus.STARTING
            self.state.start_time = time.time()
            self.state.error_message = None

            cmd = self._build_ffmpeg_command()
            logger.info("Starting FFmpeg process")

            try:
                self._process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )

                # Start stderr reader
                if self._process.stderr:
                    asyncio.create_task(self._read_stderr(self._process.stderr))

                # Wait a bit for initial stream setup
                await asyncio.sleep(2)

                if self._process.returncode is None:
                    self.state.status = StreamStatus.STREAMING
                    logger.info("FFmpeg process started", pid=self._process.pid)
                else:
                    self.state.status = StreamStatus.ERROR
                    self.state.error_message = (
                        f"FFmpeg failed to start (exit code: {self._process.returncode})"
                    )
                    logger.error(
                        "FFmpeg failed to start",
                        return_code=self._process.returncode,
                    )

            except FileNotFoundError:
                self.state.status = StreamStatus.ERROR
                self.state.error_message = "FFmpeg not found - please install ffmpeg"
                logger.error("FFmpeg not found")
            except Exception as e:
                self.state.status = StreamStatus.ERROR
                self.state.error_message = str(e)
                logger.error("Failed to start FFmpeg", error=str(e))

    async def _stop_process(self) -> None:
        """Stop the FFmpeg process gracefully."""
        async with self._lock:
            if self._process is None:
                return

            logger.info("Stopping FFmpeg process", pid=self._process.pid)

            try:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("FFmpeg didn't terminate, killing")
                    self._process.kill()
                    await self._process.wait()
            except ProcessLookupError:
                pass  # Process already exited
            except Exception as e:
                logger.error("Error stopping FFmpeg", error=str(e))
            finally:
                self._process = None

    # =========================================================================
    # Public API
    # =========================================================================

    async def start_stream(self) -> bool:
        """Start the HLS stream.

        Returns:
            True if stream started successfully, False otherwise.
        """
        if not self.config.enabled:
            logger.info("Baby monitor is disabled")
            return False

        if not self.active_rtsp_url:
            logger.warning("No RTSP URL configured for baby monitor")
            return False

        # Check if ffmpeg is available
        if not shutil.which("ffmpeg"):
            self.state.status = StreamStatus.ERROR
            self.state.error_message = "FFmpeg not found - please install ffmpeg"
            logger.error("FFmpeg not installed")
            return False

        logger.info("Starting baby monitor stream")
        self._shutdown_event.clear()

        # Start FFmpeg process
        await self._start_process()

        # Start health monitor
        self._monitor_task = asyncio.create_task(self._monitor_stream())

        return self.state.status == StreamStatus.STREAMING

    async def stop_stream(self) -> None:
        """Stop the HLS stream."""
        logger.info("Stopping baby monitor stream")
        self._shutdown_event.set()

        # Cancel monitor task
        if self._monitor_task:
            self._monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitor_task
            self._monitor_task = None

        # Stop FFmpeg process
        await self._stop_process()

        # Cleanup segments
        self._cleanup_segments()

        self.state = StreamState()
        logger.info("Baby monitor stream stopped")

    async def restart_stream(self) -> None:
        """Restart the HLS stream."""
        logger.info("Restarting baby monitor stream")
        await self._stop_process()
        self.state.reconnect_attempts = 0
        await self._start_process()

    async def capture_thumbnail(self, force: bool = False) -> bytes | None:
        """Capture a single frame thumbnail from the RTSP stream.

        Args:
            force: Force refresh even if cached thumbnail is recent

        Returns:
            JPEG image bytes or None if capture fails
        """
        # Return cached thumbnail if recent (less than 30 seconds old)
        if not force and self._thumbnail_cache:
            age = time.time() - self._thumbnail_timestamp
            if age < 30:
                return self._thumbnail_cache

        if not self.active_rtsp_url:
            logger.warning("No RTSP URL for thumbnail capture")
            return None

        if not shutil.which("ffmpeg"):
            logger.error("FFmpeg not installed for thumbnail capture")
            return None

        self._ensure_output_dir()

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            self.config.transport,
            "-i",
            self.active_rtsp_url,
            "-frames:v",
            "1",
            "-q:v",
            "2",  # JPEG quality (2 = high quality)
            "-y",  # Overwrite output
            str(self.thumbnail_path),
        ]

        try:
            logger.debug("Capturing thumbnail")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

            _, stderr = await asyncio.wait_for(process.communicate(), timeout=10.0)

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                logger.error("Thumbnail capture failed", error=error_msg)
                return None

            if self.thumbnail_path.exists():
                self._thumbnail_cache = self.thumbnail_path.read_bytes()
                self._thumbnail_timestamp = time.time()
                logger.debug("Thumbnail captured", size=len(self._thumbnail_cache))
                return self._thumbnail_cache

            return None

        except asyncio.TimeoutError:
            logger.error("Thumbnail capture timed out")
            return None
        except Exception as e:
            logger.error("Thumbnail capture error", error=str(e))
            return None

    async def discover_cameras(self, timeout: int = 5) -> list[CameraInfo]:
        """Discover ONVIF cameras on the network.

        Args:
            timeout: Discovery timeout in seconds

        Returns:
            List of discovered cameras with their RTSP URLs
        """
        cameras: list[CameraInfo] = []

        try:
            from wsdiscovery.discovery import ThreadedWSDiscovery

            logger.info("Starting ONVIF camera discovery", timeout=timeout)

            wsd = ThreadedWSDiscovery()
            wsd.start()

            # Search for ONVIF network video transmitters
            services = wsd.searchServices(
                timeout=timeout,
                types=[
                    "dn:NetworkVideoTransmitter",
                    "tds:Device",
                ],
            )

            wsd.stop()

            logger.info("WS-Discovery found services", count=len(services))

            for service in services:
                try:
                    xaddrs = service.getXAddrs()
                    if not xaddrs:
                        continue

                    # Get the first address (ONVIF service endpoint)
                    onvif_url = xaddrs[0]
                    logger.debug("Found ONVIF device", url=onvif_url)

                    # Extract host from URL
                    from urllib.parse import urlparse

                    parsed = urlparse(onvif_url)
                    host = parsed.hostname

                    if not host:
                        continue

                    # Try to get RTSP URL via ONVIF
                    rtsp_url = await self._get_rtsp_url_via_onvif(host)

                    camera = CameraInfo(
                        name=f"Camera at {host}",
                        rtsp_url=rtsp_url or "",
                        onvif_address=host,
                    )
                    cameras.append(camera)

                except Exception as e:
                    logger.debug("Error processing service", error=str(e))
                    continue

            logger.info("ONVIF discovery complete", cameras_found=len(cameras))

        except ImportError:
            logger.warning("wsdiscovery not installed, skipping discovery")
        except Exception as e:
            logger.error("ONVIF discovery failed", error=str(e))

        return cameras

    async def _get_rtsp_url_via_onvif(self, host: str, port: int = 80) -> str | None:
        """Query ONVIF device for its RTSP stream URL.

        Args:
            host: Device IP address
            port: ONVIF port (default 80)

        Returns:
            RTSP URL or None if query fails
        """
        try:
            from onvif import ONVIFCamera

            logger.debug("Querying ONVIF device", host=host, port=port)

            # Try common credentials
            credentials = [
                ("admin", "admin"),
                ("admin", ""),
                ("root", "root"),
                ("admin", "password"),
            ]

            for username, password in credentials:
                try:
                    camera = ONVIFCamera(
                        host,
                        port,
                        username,
                        password,
                        no_cache=True,
                    )

                    await camera.update_xaddrs()
                    media_service = await camera.create_media_service()
                    profiles = await media_service.GetProfiles()

                    if profiles:
                        profile_token = profiles[0].token
                        stream_setup = {
                            "Stream": "RTP-Unicast",
                            "Transport": {"Protocol": "RTSP"},
                        }
                        uri_response = await media_service.GetStreamUri(
                            {"ProfileToken": profile_token, "StreamSetup": stream_setup}
                        )

                        if uri_response and hasattr(uri_response, "Uri"):
                            rtsp_url: str = str(uri_response.Uri)
                            logger.info("Got RTSP URL via ONVIF", host=host)
                            return rtsp_url

                except Exception:
                    continue

            logger.debug("Could not get RTSP URL via ONVIF", host=host)
            return None

        except ImportError:
            logger.warning("onvif-zeep-async not installed")
            return None
        except Exception as e:
            logger.debug("ONVIF query failed", host=host, error=str(e))
            return None

    def set_active_camera(self, camera: CameraInfo) -> None:
        """Set the active camera for streaming.

        Args:
            camera: Camera to use for streaming
        """
        self._active_camera = camera
        logger.info("Set active camera", name=camera.name)

    def get_status(self) -> dict[str, Any]:
        """Get current stream status as a dictionary."""
        safe_url = self._mask_rtsp_url(self.active_rtsp_url) if self.active_rtsp_url else ""

        return {
            "status": self.state.status.value,
            "uptime_seconds": self.uptime_seconds,
            "camera": {
                "name": self._active_camera.name if self._active_camera else None,
                "url": safe_url,
                "connected": self.is_streaming,
                "resolution": self.state.resolution,
                "fps": self.state.fps,
            },
            "reconnect_attempts": self.state.reconnect_attempts,
            "error": self.state.error_message,
            "enabled": self.config.enabled,
            "has_thumbnail": self._thumbnail_cache is not None,
        }

    def get_thumbnail_age(self) -> float:
        """Get age of cached thumbnail in seconds."""
        if self._thumbnail_timestamp == 0:
            return float("inf")
        return time.time() - self._thumbnail_timestamp
