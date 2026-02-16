"""Tests for DockerRunner."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from orchestrator.runner import DockerRunner


def _make_process(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
    """Create a mock async subprocess."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    proc.wait = AsyncMock()
    return proc


@pytest.fixture
def runner():
    return DockerRunner(project_name="test-project")


async def test_run_ephemeral_success(runner):
    """Successful ephemeral run returns True."""
    proc = _make_process(returncode=0)
    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        result = await runner.run_ephemeral("source-pihole")

    assert result is True
    # Verify the command constructed
    cmd = mock_exec.call_args[0]
    assert cmd == (
        "docker",
        "compose",
        "-p",
        "test-project",
        "--profile",
        "poll",
        "run",
        "--rm",
        "source-pihole",
    )
    # Should no longer be in running set
    assert "source-pihole" not in runner.running


async def test_run_ephemeral_failure(runner):
    """Failed ephemeral run returns False."""
    proc = _make_process(returncode=1, stdout=b"out", stderr=b"err")
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        result = await runner.run_ephemeral("source-pihole")

    assert result is False
    assert "source-pihole" not in runner.running


async def test_run_ephemeral_with_env(runner):
    """Environment variables are passed as -e flags."""
    proc = _make_process(returncode=0)
    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        result = await runner.run_ephemeral("source-aranet4", env={"MODE": "scan"})

    assert result is True
    cmd = mock_exec.call_args[0]
    assert "-e" in cmd
    idx = cmd.index("-e")
    assert cmd[idx + 1] == "MODE=scan"


async def test_run_ephemeral_timeout(runner):
    """Timeout kills the process and returns False."""
    proc = _make_process(returncode=0)
    proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
    proc.kill = MagicMock()
    proc.wait = AsyncMock()

    with patch("asyncio.create_subprocess_exec", return_value=proc):

        async def mock_wait_for(coro, timeout):
            # Consume the coroutine
            try:
                raise TimeoutError
            finally:
                coro.close()

        with patch("asyncio.wait_for", side_effect=mock_wait_for):
            result = await runner.run_ephemeral("source-pihole", timeout=0.01)

    assert result is False
    proc.kill.assert_called_once()
    assert "source-pihole" not in runner.running


async def test_double_spawn_prevention(runner):
    """Same service cannot be spawned twice concurrently."""
    started = asyncio.Event()
    finish = asyncio.Event()

    async def slow_communicate():
        started.set()
        await finish.wait()
        return (b"", b"")

    proc = _make_process(returncode=0)
    proc.communicate = slow_communicate

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        # Start first run
        task1 = asyncio.create_task(runner.run_ephemeral("source-pihole"))
        await started.wait()

        # Attempt second run while first is still running
        result2 = await runner.run_ephemeral("source-pihole")

        # Second should be rejected
        assert result2 is False

        # Let first finish
        finish.set()
        result1 = await task1
        assert result1 is True

    assert "source-pihole" not in runner.running


async def test_start_service_success(runner):
    """Successful start_service returns True."""
    proc = _make_process(returncode=0)
    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        result = await runner.start_service("source-camera")

    assert result is True
    cmd = mock_exec.call_args[0]
    assert cmd == (
        "docker",
        "compose",
        "-p",
        "test-project",
        "--profile",
        "camera",
        "up",
        "-d",
        "source-camera",
    )
    # Should remain in running set (it's a long-running service)
    assert "source-camera" in runner.running


async def test_start_service_failure(runner):
    """Failed start_service returns False and removes from running set."""
    proc = _make_process(returncode=1, stderr=b"error")
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        result = await runner.start_service("source-camera")

    assert result is False
    assert "source-camera" not in runner.running


async def test_stop_service_success(runner):
    """Successful stop_service returns True and removes from running set."""
    # Pre-add to running set
    runner._running.add("source-camera")

    proc = _make_process(returncode=0)
    with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
        result = await runner.stop_service("source-camera")

    assert result is True
    cmd = mock_exec.call_args[0]
    assert cmd == (
        "docker",
        "compose",
        "-p",
        "test-project",
        "--profile",
        "camera",
        "stop",
        "source-camera",
    )
    assert "source-camera" not in runner.running


async def test_stop_service_failure(runner):
    """Failed stop_service returns False."""
    proc = _make_process(returncode=1, stderr=b"not running")
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        result = await runner.stop_service("source-camera")

    assert result is False


async def test_start_service_double_spawn_prevention(runner):
    """Cannot start a service that is already running."""
    # Start it first
    proc = _make_process(returncode=0)
    with patch("asyncio.create_subprocess_exec", return_value=proc):
        result1 = await runner.start_service("source-camera")
    assert result1 is True

    # Try starting again
    result2 = await runner.start_service("source-camera")
    assert result2 is False


async def test_project_name_from_env():
    """Project name falls back to COMPOSE_PROJECT_NAME env var."""
    with patch.dict("os.environ", {"COMPOSE_PROJECT_NAME": "my-project"}):
        runner = DockerRunner()
    assert runner.project_name == "my-project"
