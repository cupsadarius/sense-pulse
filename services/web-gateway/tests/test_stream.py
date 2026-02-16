"""Tests for GET /api/stream/{path:path} endpoint."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_stream_playlist_not_exists(client: AsyncClient):
    """GET /api/stream/stream.m3u8 returns 503 if playlist doesn't exist."""
    with patch.object(Path, "exists", return_value=False):
        resp = await client.get("/api/stream/stream.m3u8")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_stream_segment_not_found(client: AsyncClient):
    """GET /api/stream/seg001.ts returns 404 if segment missing."""
    with patch.object(Path, "exists", return_value=False):
        resp = await client.get("/api/stream/seg001.ts")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_stream_unsupported_file(client: AsyncClient):
    """GET /api/stream/file.txt returns 400 for unsupported type."""
    resp = await client.get("/api/stream/file.txt")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_stream_path_traversal(client: AsyncClient):
    """GET /api/stream/../etc/passwd is sanitized to just 'passwd'."""
    # The path will be sanitized to "passwd" which is not .m3u8 or .ts
    resp = await client.get("/api/stream/../etc/passwd")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_stream_playlist_served(client: AsyncClient, tmp_path: Path):
    """GET /api/stream/stream.m3u8 serves playlist when file exists."""
    import gateway.routes.stream as stream_mod

    # Create a temp HLS dir with a playlist
    playlist = tmp_path / "stream.m3u8"
    playlist.write_text("#EXTM3U\n#EXTINF:6.0,\nseg001.ts\n")

    original_hls = stream_mod.HLS_DIR
    stream_mod.HLS_DIR = tmp_path
    try:
        resp = await client.get("/api/stream/stream.m3u8")
        assert resp.status_code == 200
        assert "mpegurl" in resp.headers["content-type"]
        assert "no-cache" in resp.headers["cache-control"]
    finally:
        stream_mod.HLS_DIR = original_hls


@pytest.mark.asyncio
async def test_stream_segment_served(client: AsyncClient, tmp_path: Path):
    """GET /api/stream/seg001.ts serves segment when file exists."""
    import gateway.routes.stream as stream_mod

    segment = tmp_path / "seg001.ts"
    segment.write_bytes(b"\x00" * 100)

    original_hls = stream_mod.HLS_DIR
    stream_mod.HLS_DIR = tmp_path
    try:
        resp = await client.get("/api/stream/seg001.ts")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "video/mp2t"
    finally:
        stream_mod.HLS_DIR = original_hls
