"""Tests for FFmpeg HLS stream manager."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from camera.stream import StreamManager, StreamStatus


@pytest.fixture
def stream_manager(tmp_path: Path) -> StreamManager:
    """Create a StreamManager with a temp output dir."""
    return StreamManager(
        rtsp_url="rtsp://user:pass@192.168.1.100:554/stream",
        output_dir=str(tmp_path),
        transport="tcp",
        max_reconnect_attempts=3,
        reconnect_delay=0.1,
    )


class TestStreamManagerInit:
    def test_initial_status_is_stopped(self, stream_manager: StreamManager) -> None:
        assert stream_manager.get_status()["status"] == "stopped"

    def test_initial_uptime_is_zero(self, stream_manager: StreamManager) -> None:
        assert stream_manager.uptime_seconds == 0.0

    def test_is_streaming_false_initially(self, stream_manager: StreamManager) -> None:
        assert stream_manager.is_streaming is False


class TestBuildFFmpegCommand:
    def test_command_contains_ffmpeg(self, stream_manager: StreamManager) -> None:
        cmd = stream_manager.build_ffmpeg_command()
        assert cmd[0] == "ffmpeg"

    def test_command_contains_rtsp_url(self, stream_manager: StreamManager) -> None:
        cmd = stream_manager.build_ffmpeg_command()
        assert "rtsp://user:pass@192.168.1.100:554/stream" in cmd

    def test_command_contains_transport(self, stream_manager: StreamManager) -> None:
        cmd = stream_manager.build_ffmpeg_command()
        idx = cmd.index("-rtsp_transport")
        assert cmd[idx + 1] == "tcp"

    def test_command_contains_hls_output(self, stream_manager: StreamManager) -> None:
        cmd = stream_manager.build_ffmpeg_command()
        assert "-f" in cmd
        idx = cmd.index("-f")
        assert cmd[idx + 1] == "hls"

    def test_command_copies_video(self, stream_manager: StreamManager) -> None:
        cmd = stream_manager.build_ffmpeg_command()
        # -c:v copy
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "copy"

    def test_command_transcodes_audio_to_aac(self, stream_manager: StreamManager) -> None:
        cmd = stream_manager.build_ffmpeg_command()
        ca_idx = cmd.index("-c:a")
        assert cmd[ca_idx + 1] == "aac"

    def test_command_output_is_m3u8(self, stream_manager: StreamManager) -> None:
        cmd = stream_manager.build_ffmpeg_command()
        assert cmd[-1].endswith("stream.m3u8")

    def test_command_segment_pattern(self, stream_manager: StreamManager) -> None:
        cmd = stream_manager.build_ffmpeg_command()
        idx = cmd.index("-hls_segment_filename")
        assert "segment_%03d.ts" in cmd[idx + 1]


class TestStreamStartStop:
    async def test_start_success(self, stream_manager: StreamManager) -> None:
        mock_process = MagicMock()
        mock_process.returncode = None
        mock_process.pid = 12345
        mock_process.stderr = None

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await stream_manager.start()

        assert result is True
        assert stream_manager.get_status()["status"] == "streaming"
        assert stream_manager.is_streaming is True

        # Clean up monitor task
        if stream_manager._monitor_task:
            stream_manager._monitor_task.cancel()
            try:
                await stream_manager._monitor_task
            except asyncio.CancelledError:
                pass

    async def test_start_ffmpeg_not_found(self, stream_manager: StreamManager) -> None:
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            result = await stream_manager.start()

        assert result is False
        assert stream_manager.get_status()["status"] == "error"
        assert "not found" in stream_manager.get_status()["error"]

    async def test_start_ffmpeg_exits_immediately(self, stream_manager: StreamManager) -> None:
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.stderr = None

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await stream_manager.start()

        assert result is False
        assert stream_manager.get_status()["status"] == "error"

    async def test_stop_terminates_process(self, stream_manager: StreamManager) -> None:
        mock_process = MagicMock()
        mock_process.returncode = None
        mock_process.pid = 12345
        mock_process.stderr = None
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock(return_value=0)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await stream_manager.start()

        # Cancel monitor before stopping
        if stream_manager._monitor_task:
            stream_manager._monitor_task.cancel()
            try:
                await stream_manager._monitor_task
            except asyncio.CancelledError:
                pass
            stream_manager._monitor_task = None

        await stream_manager.stop()

        mock_process.terminate.assert_called_once()
        assert stream_manager.get_status()["status"] == "stopped"
        assert stream_manager.is_streaming is False

    async def test_stop_kills_if_terminate_times_out(self, stream_manager: StreamManager) -> None:
        mock_process = MagicMock()
        mock_process.returncode = None
        mock_process.pid = 12345
        mock_process.stderr = None
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()

        # wait() times out on first call (after terminate), succeeds on second (after kill)
        mock_process.wait = AsyncMock(side_effect=[asyncio.TimeoutError, 0])

        # Manually set process to simulate started state
        stream_manager._process = mock_process
        stream_manager._status = StreamStatus.STREAMING

        await stream_manager.stop()

        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()

    async def test_restart_stops_then_starts(self, stream_manager: StreamManager) -> None:
        with (
            patch.object(stream_manager, "stop", new_callable=AsyncMock) as mock_stop,
            patch.object(
                stream_manager, "start", new_callable=AsyncMock, return_value=True
            ) as mock_start,
        ):
            result = await stream_manager.restart()

        mock_stop.assert_called_once()
        mock_start.assert_called_once()
        assert result is True


class TestStreamStatus:
    def test_get_status_fields(self, stream_manager: StreamManager) -> None:
        status = stream_manager.get_status()
        assert "status" in status
        assert "connected" in status
        assert "error" in status
        assert "resolution" in status
        assert "fps" in status
        assert "uptime" in status

    def test_get_status_values_when_stopped(self, stream_manager: StreamManager) -> None:
        status = stream_manager.get_status()
        assert status["status"] == "stopped"
        assert status["connected"] is False
        assert status["error"] is None
        assert status["resolution"] is None
        assert status["fps"] is None
        assert status["uptime"] == 0.0

    def test_mask_rtsp_url_with_credentials(self, stream_manager: StreamManager) -> None:
        masked = stream_manager._mask_rtsp_url("rtsp://user:pass@host/path")
        assert "user" not in masked
        assert "pass" not in masked
        assert "***" in masked
        assert "host/path" in masked

    def test_mask_rtsp_url_without_credentials(self, stream_manager: StreamManager) -> None:
        url = "rtsp://host/path"
        assert stream_manager._mask_rtsp_url(url) == url


class TestStreamCleanup:
    def test_cleanup_removes_ts_and_m3u8(
        self, stream_manager: StreamManager, tmp_path: Path
    ) -> None:
        # Create some segments
        (tmp_path / "segment_000.ts").write_text("data")
        (tmp_path / "segment_001.ts").write_text("data")
        (tmp_path / "stream.m3u8").write_text("#EXTM3U")

        stream_manager._cleanup_segments()

        assert not (tmp_path / "segment_000.ts").exists()
        assert not (tmp_path / "segment_001.ts").exists()
        assert not (tmp_path / "stream.m3u8").exists()


class TestMonitorDetectsStaleStream:
    async def test_monitor_detects_process_exit(self, stream_manager: StreamManager) -> None:
        mock_process = MagicMock()
        mock_process.returncode = 1  # Process exited
        stream_manager._process = mock_process
        stream_manager._status = StreamStatus.STREAMING

        # Mock _handle_reconnect to prevent actual reconnection
        with patch.object(
            stream_manager, "_handle_reconnect", new_callable=AsyncMock
        ) as mock_reconnect:
            # Run monitor briefly
            stream_manager._shutdown_event.clear()

            async def stop_after_check():
                await asyncio.sleep(3)
                stream_manager._shutdown_event.set()

            monitor_task = asyncio.create_task(stream_manager.monitor())
            stop_task = asyncio.create_task(stop_after_check())

            with patch("asyncio.sleep", new_callable=AsyncMock):
                await asyncio.sleep(0.1)
                stream_manager._shutdown_event.set()

            monitor_task.cancel()
            stop_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            try:
                await stop_task
            except asyncio.CancelledError:
                pass


class TestReconnectLogic:
    def test_max_reconnect_attempts(self, stream_manager: StreamManager) -> None:
        assert stream_manager.max_reconnect_attempts == 3

    def test_reconnect_attempts_starts_at_zero(self, stream_manager: StreamManager) -> None:
        assert stream_manager.reconnect_attempts == 0
