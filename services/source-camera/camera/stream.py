"""FFmpeg HLS stream manager.

Manages RTSP to HLS transcoding via FFmpeg subprocess.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class StreamStatus(Enum):
    """Stream status states."""

    STOPPED = "stopped"
    STARTING = "starting"
    STREAMING = "streaming"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class StreamManager:
    """Manages FFmpeg HLS streaming from an RTSP source.

    Handles:
    - FFmpeg subprocess lifecycle (start, stop, restart)
    - RTSP to HLS transcoding
    - Automatic reconnection with exponential backoff
    - Stream health monitoring
    - HLS segment cleanup
    """

    def __init__(
        self,
        rtsp_url: str,
        output_dir: str = "/hls",
        transport: str = "tcp",
        hls_segment_duration: int = 2,
        hls_playlist_size: int = 5,
        max_reconnect_attempts: int = 10,
        reconnect_delay: float = 5.0,
    ) -> None:
        self._rtsp_url = rtsp_url
        self._output_dir = Path(output_dir)
        self._transport = transport
        self._hls_segment_duration = hls_segment_duration
        self._hls_playlist_size = hls_playlist_size
        self._max_reconnect_attempts = max_reconnect_attempts
        self._reconnect_delay = reconnect_delay

        self._process: asyncio.subprocess.Process | None = None
        self._monitor_task: asyncio.Task[None] | None = None
        self._shutdown_event = asyncio.Event()
        self._lock = asyncio.Lock()

        # Stream state
        self._status = StreamStatus.STOPPED
        self._start_time: float | None = None
        self._error_message: str | None = None
        self._reconnect_attempts = 0
        self._resolution: str | None = None
        self._fps: int | None = None

    @property
    def playlist_path(self) -> Path:
        return self._output_dir / "stream.m3u8"

    @property
    def is_streaming(self) -> bool:
        return self._status == StreamStatus.STREAMING

    @property
    def uptime_seconds(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def _mask_rtsp_url(self, url: str) -> str:
        """Mask credentials in RTSP URL for logging."""
        if "@" in url:
            parts = url.split("@", 1)
            protocol = parts[0].split("://")[0]
            host_and_path = parts[1]
            return f"{protocol}://***@{host_and_path}"
        return url

    def _ensure_output_dir(self) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def _cleanup_segments(self) -> None:
        """Remove all HLS segments and playlist."""
        if self._output_dir.exists():
            for f in self._output_dir.glob("*.ts"):
                with contextlib.suppress(OSError):
                    f.unlink()
            with contextlib.suppress(OSError):
                if self.playlist_path.exists():
                    self.playlist_path.unlink()

    def build_ffmpeg_command(self) -> list[str]:
        """Build the FFmpeg command for RTSP to HLS transcoding."""
        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-use_wallclock_as_timestamps",
            "1",
            "-fflags",
            "+genpts+nobuffer+discardcorrupt",
            "-flags",
            "low_delay",
            "-rtsp_transport",
            self._transport,
            "-i",
            self._rtsp_url,
            # Video: copy H.264 (no transcode)
            "-c:v",
            "copy",
            # Audio: transcode to AAC for browser compatibility
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            # HLS output
            "-f",
            "hls",
            "-hls_time",
            str(self._hls_segment_duration),
            "-hls_list_size",
            str(self._hls_playlist_size),
            "-hls_flags",
            "delete_segments+program_date_time",
            "-start_number",
            "0",
            "-hls_segment_filename",
            str(self._output_dir / "segment_%03d.ts"),
            str(self.playlist_path),
        ]

    async def _read_stderr(self, stderr: asyncio.StreamReader) -> None:
        """Read and parse FFmpeg stderr output for resolution/fps info."""
        while True:
            try:
                line = await stderr.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded:
                    if "Video:" in decoded and "x" in decoded:
                        match = re.search(r"(\d{3,4})x(\d{3,4})", decoded)
                        if match:
                            self._resolution = f"{match.group(1)}x{match.group(2)}"
                        fps_match = re.search(r"(\d+(?:\.\d+)?)\s*fps", decoded)
                        if fps_match:
                            self._fps = int(float(fps_match.group(1)))
                    logger.debug("FFmpeg: %s", decoded)
            except Exception:
                break

    async def start(self) -> bool:
        """Start the FFmpeg HLS stream.

        Returns:
            True if stream started successfully, False otherwise.
        """
        async with self._lock:
            if self._process is not None:
                return True

            self._ensure_output_dir()
            self._cleanup_segments()
            self._shutdown_event.clear()

            self._status = StreamStatus.STARTING
            self._start_time = time.time()
            self._error_message = None

            cmd = self.build_ffmpeg_command()
            logger.info("Starting FFmpeg: %s", self._mask_rtsp_url(self._rtsp_url))

            try:
                self._process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )

                if self._process.stderr:
                    asyncio.create_task(self._read_stderr(self._process.stderr))

                # Brief wait for startup
                await asyncio.sleep(2)

                if self._process.returncode is None:
                    self._status = StreamStatus.STREAMING
                    logger.info("FFmpeg started: pid=%s", self._process.pid)

                    # Start monitor
                    self._monitor_task = asyncio.create_task(self.monitor())
                    return True
                else:
                    self._status = StreamStatus.ERROR
                    self._error_message = (
                        f"FFmpeg failed to start (exit code: {self._process.returncode})"
                    )
                    logger.error("FFmpeg failed to start: rc=%s", self._process.returncode)
                    self._process = None
                    return False

            except FileNotFoundError:
                self._status = StreamStatus.ERROR
                self._error_message = "FFmpeg not found"
                logger.error("FFmpeg not found")
                return False
            except Exception as e:
                self._status = StreamStatus.ERROR
                self._error_message = str(e)
                logger.error("Failed to start FFmpeg: %s", e)
                return False

    async def stop(self) -> None:
        """Stop the FFmpeg stream gracefully."""
        self._shutdown_event.set()

        # Cancel monitor
        if self._monitor_task:
            self._monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitor_task
            self._monitor_task = None

        # Stop FFmpeg process
        async with self._lock:
            if self._process is not None:
                logger.info("Stopping FFmpeg: pid=%s", self._process.pid)
                try:
                    self._process.terminate()
                    try:
                        await asyncio.wait_for(self._process.wait(), timeout=5.0)
                    except TimeoutError:
                        logger.warning("FFmpeg didn't terminate, killing")
                        self._process.kill()
                        await self._process.wait()
                except ProcessLookupError:
                    pass
                except Exception as e:
                    logger.error("Error stopping FFmpeg: %s", e)
                finally:
                    self._process = None

        self._cleanup_segments()

        self._status = StreamStatus.STOPPED
        self._start_time = None
        self._error_message = None
        self._reconnect_attempts = 0
        self._resolution = None
        self._fps = None
        logger.info("Stream stopped")

    async def restart(self) -> bool:
        """Restart the HLS stream."""
        logger.info("Restarting stream")
        await self.stop()
        return await self.start()

    def get_status(self) -> dict[str, Any]:
        """Return current stream status as a dictionary."""
        return {
            "status": self._status.value,
            "connected": self.is_streaming,
            "error": self._error_message,
            "resolution": self._resolution,
            "fps": self._fps,
            "uptime": self.uptime_seconds,
        }

    async def monitor(self) -> None:
        """Background loop to monitor stream health and handle reconnection."""
        stale_threshold = 10  # seconds

        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(2)

                if self._process is None:
                    continue

                # Check if process exited
                if self._process.returncode is not None:
                    logger.warning("FFmpeg exited: rc=%s", self._process.returncode)
                    self._status = StreamStatus.ERROR
                    self._error_message = f"FFmpeg exited with code {self._process.returncode}"
                    self._process = None
                    await self._handle_reconnect()
                    continue

                # Check for stale playlist
                if self.playlist_path.exists():
                    age = time.time() - self.playlist_path.stat().st_mtime
                    if age > stale_threshold:
                        logger.warning("Stream stale: segment_age=%.1fs", age)
                        self._status = StreamStatus.ERROR
                        self._error_message = "Stream stale - no new segments"
                        await self._handle_reconnect()
                    elif self._status != StreamStatus.STREAMING:
                        self._status = StreamStatus.STREAMING
                        self._error_message = None
                        self._reconnect_attempts = 0

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Monitor error: %s", e)

    async def _handle_reconnect(self) -> None:
        """Handle stream reconnection with exponential backoff.

        Returns True if reconnect was attempted, False if max attempts reached.
        """
        if (
            self._max_reconnect_attempts != -1
            and self._reconnect_attempts >= self._max_reconnect_attempts
        ):
            logger.error("Max reconnect attempts reached: %d", self._reconnect_attempts)
            self._status = StreamStatus.ERROR
            self._error_message = "Max reconnect attempts reached"
            return

        self._status = StreamStatus.RECONNECTING
        self._reconnect_attempts += 1

        delay = min(
            self._reconnect_delay * (2 ** (self._reconnect_attempts - 1)),
            60,
        )
        logger.info("Reconnecting: attempt=%d delay=%.0fs", self._reconnect_attempts, delay)

        # Stop current process
        async with self._lock:
            if self._process is not None:
                try:
                    self._process.terminate()
                    try:
                        await asyncio.wait_for(self._process.wait(), timeout=5.0)
                    except TimeoutError:
                        self._process.kill()
                        await self._process.wait()
                except ProcessLookupError:
                    pass
                finally:
                    self._process = None

        await asyncio.sleep(delay)

        if not self._shutdown_event.is_set():
            # Restart FFmpeg
            self._ensure_output_dir()
            self._cleanup_segments()
            cmd = self.build_ffmpeg_command()
            try:
                async with self._lock:
                    self._process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    if self._process.stderr:
                        asyncio.create_task(self._read_stderr(self._process.stderr))

                await asyncio.sleep(2)
                if self._process and self._process.returncode is None:
                    self._status = StreamStatus.STREAMING
                    self._error_message = None
                    logger.info("Reconnected: pid=%s", self._process.pid)
            except Exception as e:
                self._status = StreamStatus.ERROR
                self._error_message = str(e)
                logger.error("Reconnect failed: %s", e)

    @property
    def max_reconnect_attempts(self) -> int:
        return self._max_reconnect_attempts

    @property
    def reconnect_attempts(self) -> int:
        return self._reconnect_attempts
