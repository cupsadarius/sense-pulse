"""Tests for WebSocket endpoints.

These tests use Starlette's synchronous ``TestClient`` which runs its own
event loop.  To avoid the "bound to a different event loop" error with
fakeredis we create a shared ``FakeServer``, seed it with synchronous
``FakeRedis``, and then attach an *async* ``FakeRedis`` (same server) to
the app inside the test — so the async client is always created on the
TestClient's own loop.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import fakeredis
import fakeredis.aioredis
from gateway.app import create_app
from starlette.testclient import TestClient


def _seed_server(server: fakeredis.FakeServer) -> None:
    """Write the minimal test data into *server* using a sync client."""
    r = fakeredis.FakeRedis(server=server, decode_responses=True)

    r.set(
        "source:system:cpu_percent",
        json.dumps({"value": 23.5, "unit": "%", "timestamp": 1708000000.0}),
        ex=60,
    )
    r.set(
        "source:system:memory_percent",
        json.dumps({"value": 61.2, "unit": "%", "timestamp": 1708000000.0}),
        ex=60,
    )

    r.set(
        "status:system",
        json.dumps(
            {
                "source_id": "system",
                "last_poll": 1708000000.0,
                "last_success": 1708000000.0,
                "last_error": None,
                "poll_count": 100,
                "error_count": 0,
            }
        ),
        ex=120,
    )

    # Auth disabled so WebSocket endpoints don't require credentials
    r.set(
        "config:auth",
        json.dumps({"enabled": False, "username": "admin", "password_hash": ""}),
    )

    r.close()


def _make_app(server: fakeredis.FakeServer):
    """Create a FastAPI app wired to *server*."""
    app = create_app()
    # The async FakeRedis will be created on whatever loop is running when
    # the first command is executed — i.e. the TestClient's loop.
    app.state.redis = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    return app


def test_ws_sources_initial_snapshot():
    """WS /ws/sources sends initial snapshot on connect."""
    server = fakeredis.FakeServer()
    _seed_server(server)
    app = _make_app(server)

    # Shrink timeouts so the handler exits quickly after client disconnects.
    # After receiving the snapshot the client closes; the handler's next
    # poll-fallback will attempt send_json → WebSocketDisconnect → clean exit.
    with (
        patch("gateway.websocket.sources.BATCH_INTERVAL", 0.1),
        patch("gateway.websocket.sources.POLL_FALLBACK", 0.2),
        patch("gateway.websocket.sources.HEARTBEAT_INTERVAL", 0.2),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        with client.websocket_connect("/ws/sources") as ws:
            data = ws.receive_json()
            # Should have the same shape as GET /api/sources
            assert "system" in data
            assert "readings" in data["system"]
            assert "status" in data["system"]
            assert data["system"]["readings"]["cpu_percent"]["value"] == 23.5


def test_ws_grid_connect():
    """WS /ws/grid accepts the connection (smoke test).

    The grid handler enters an infinite pub/sub loop after accepting, so we
    just verify the upgrade succeeds and the server doesn't reject.  We
    immediately close and suppress the server-side error from the handler
    trying to use the disconnected websocket.
    """
    server = fakeredis.FakeServer()
    _seed_server(server)
    app = _make_app(server)

    client = TestClient(app, raise_server_exceptions=False)
    with client.websocket_connect("/ws/grid") as ws:
        ws.close()
