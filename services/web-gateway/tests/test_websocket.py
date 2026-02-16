"""Tests for WebSocket endpoints."""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient


def test_ws_sources_initial_snapshot(app):
    """WS /ws/sources sends initial snapshot on connect."""
    client = TestClient(app)
    with client.websocket_connect("/ws/sources") as ws:
        data = ws.receive_json()
        # Should have the same shape as GET /api/sources
        assert "system" in data
        assert "readings" in data["system"]
        assert "status" in data["system"]
        assert data["system"]["readings"]["cpu_percent"]["value"] == 23.5


def test_ws_grid_connect(app):
    """WS /ws/grid connects successfully."""
    client = TestClient(app)
    with client.websocket_connect("/ws/grid"):
        # Grid WS connects and waits for pubsub messages.
        # Since no messages are published, just verify it connects.
        pass
