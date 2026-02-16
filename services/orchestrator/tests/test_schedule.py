"""Tests for Scheduler."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.runner import DockerRunner
from orchestrator.schedule import Scheduler


@pytest.fixture
def runner():
    """Create a DockerRunner with mocked subprocess."""
    return DockerRunner(project_name="test")


def make_scheduler(runner, schedules=None):
    """Create a scheduler with short intervals for testing."""
    s = schedules or {
        "source-tailscale": 10,
        "source-pihole": 10,
    }
    return Scheduler(runner, s)


async def test_immediate_trigger_on_startup(runner):
    """All services should be triggered immediately on startup."""
    scheduler = make_scheduler(runner)
    triggered = []

    original_run = runner.run_ephemeral

    async def mock_run(service, **kwargs):
        triggered.append(service)
        return True

    runner.run_ephemeral = mock_run

    # Run scheduler for a brief moment
    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(0.1)
    scheduler.stop()
    await task

    # Both services should have been triggered
    assert "source-tailscale" in triggered
    assert "source-pihole" in triggered


async def test_respects_interval(runner):
    """Services should not be re-triggered before their interval."""
    scheduler = make_scheduler(runner, {"source-test": 1000})
    triggered = []

    async def mock_run(service, **kwargs):
        triggered.append(service)
        return True

    runner.run_ephemeral = mock_run

    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(0.2)
    scheduler.stop()
    await task

    # Should trigger exactly once (initial trigger, then interval is 1000s)
    assert triggered.count("source-test") == 1


async def test_update_schedule(runner):
    """update_schedule should change intervals."""
    scheduler = make_scheduler(runner, {"source-tailscale": 30})

    # Update with short-form names (without source- prefix)
    scheduler.update_schedule({"tailscale": 60, "pihole": 45})

    assert scheduler.schedules["source-tailscale"] == 60
    assert scheduler.schedules["source-pihole"] == 45


async def test_update_schedule_adds_new_service(runner):
    """update_schedule should add new services."""
    scheduler = make_scheduler(runner, {"source-tailscale": 30})

    scheduler.update_schedule({"weather": 300})

    assert "source-weather" in scheduler.schedules
    assert scheduler.schedules["source-weather"] == 300
    assert "source-weather" in scheduler.last_run


async def test_skips_already_running(runner):
    """Services already running should not be triggered again."""
    scheduler = make_scheduler(runner, {"source-test": 1})
    run_count = 0

    async def mock_run(service, **kwargs):
        nonlocal run_count
        run_count += 1
        return True

    runner.run_ephemeral = mock_run
    # Pre-add to running set (simulate in-flight)
    runner._running.add("source-test")

    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(0.2)
    scheduler.stop()
    await task

    # Should not have triggered since it was "already running"
    assert run_count == 0


async def test_concurrent_services(runner):
    """Multiple services can run concurrently."""
    scheduler = make_scheduler(
        runner,
        {
            "source-a": 1000,
            "source-b": 1000,
        },
    )
    triggered = set()

    async def mock_run(service, **kwargs):
        triggered.add(service)
        return True

    runner.run_ephemeral = mock_run

    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(0.1)
    scheduler.stop()
    await task

    assert "source-a" in triggered
    assert "source-b" in triggered


async def test_stop_waits_for_tasks(runner):
    """Stopping should wait for running tasks to finish."""
    scheduler = make_scheduler(runner, {"source-test": 1000})
    finished = asyncio.Event()

    async def slow_run(service, **kwargs):
        await asyncio.sleep(0.1)
        finished.set()
        return True

    runner.run_ephemeral = slow_run

    task = asyncio.create_task(scheduler.run())
    await asyncio.sleep(0.05)
    scheduler.stop()
    await task

    # The slow task should have completed
    assert finished.is_set()
