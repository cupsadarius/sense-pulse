"""
FFmpeg-based RTSP to HLS stream manager.

Handles:
- FFmpeg subprocess lifecycle (start, stop, restart)
- RTSP to HLS transcoding
- Automatic reconnection with exponential backoff
- Stream health monitoring
- HLS segment cleanup
"""

import asyncio
import contextlib
import shutil
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

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
class StreamState:
    """Current state of the stream."""

    status: StreamStatus = StreamStatus.STOPPED
    start_time: Optional[float] = None
    last_segment_time: Optional[float] = None
    reconnect_attempts: int = 0
    error_message: Optional[str] = None
    resolution: Optional[str] = None
    fps: Optional[int] = None


@dataclass
class StreamManager:
    """
    Manages FFmpeg process for RTSP to HLS transcoding.

    Attributes:
        config: Baby monitor configuration
        state: Current stream state
    """

    config: BabyMonitorConfig
    state: StreamState = field(default_factory=StreamState)
    _process: Optional[asyncio.subprocess.Process] = None
    _monitor_task: Optional[asyncio.Task] = None
    _shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        """Initialize non-field attributes."""
        self._shutdown_event = asyncio.Event()
        self._lock = asyncio.Lock()

    @property
    def output_dir(self) -> Path:
        """Get the HLS output directory."""
        return Path(self.config.output_dir)

    @property
    def playlist_path(self) -> Path:
        """Get the HLS playlist file path."""
        return self.output_dir / "stream.m3u8"

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

    def _build_ffmpeg_command(self) -> list[str]:
        """Build the FFmpeg command for RTSP to HLS transcoding."""
        # Mask password in URL for logging
        safe_url = self.config.rtsp_url
        if "@" in safe_url:
            # Mask credentials: rtsp://user:pass@host -> rtsp://***@host
            parts = safe_url.split("@", 1)
            protocol_and_creds = parts[0]
            host_and_path = parts[1]
            protocol = protocol_and_creds.split("://")[0]
            safe_url = f"{protocol}://***@{host_and_path}"

        logger.info("Building FFmpeg command", rtsp_url=safe_url)

        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            # Input options
            "-rtsp_transport",
            self.config.transport,
            "-i",
            self.config.rtsp_url,
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
        while True:
            try:
                line = await stderr.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded:
                    # Parse resolution/fps from FFmpeg output if present
                    if "Video:" in decoded and "x" in decoded:
                        # Try to extract resolution
                        import re

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

    async def start(self) -> None:
        """Start the stream manager."""
        if not self.config.enabled:
            logger.info("Baby monitor is disabled")
            return

        if not self.config.rtsp_url:
            logger.warning("No RTSP URL configured for baby monitor")
            return

        # Check if ffmpeg is available
        if not shutil.which("ffmpeg"):
            self.state.status = StreamStatus.ERROR
            self.state.error_message = "FFmpeg not found - please install ffmpeg"
            logger.error("FFmpeg not installed")
            return

        logger.info("Starting baby monitor stream manager")
        self._shutdown_event.clear()

        # Start FFmpeg process
        await self._start_process()

        # Start health monitor
        self._monitor_task = asyncio.create_task(self._monitor_stream())

    async def stop(self) -> None:
        """Stop the stream manager."""
        logger.info("Stopping baby monitor stream manager")
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
        logger.info("Baby monitor stream manager stopped")

    async def restart(self) -> None:
        """Restart the stream."""
        logger.info("Restarting baby monitor stream")
        await self._stop_process()
        self.state.reconnect_attempts = 0
        await self._start_process()

    def get_status(self) -> dict:
        """Get current stream status as a dictionary."""
        # Mask password in URL for status
        safe_url = self.config.rtsp_url
        if "@" in safe_url:
            parts = safe_url.split("@", 1)
            protocol = parts[0].split("://")[0]
            host_and_path = parts[1]
            safe_url = f"{protocol}://***@{host_and_path}"

        return {
            "status": self.state.status.value,
            "uptime_seconds": self.uptime_seconds,
            "camera": {
                "url": safe_url,
                "connected": self.is_streaming,
                "resolution": self.state.resolution,
                "fps": self.state.fps,
            },
            "reconnect_attempts": self.state.reconnect_attempts,
            "error": self.state.error_message,
            "enabled": self.config.enabled,
        }
