"""Tests for authentication."""

from __future__ import annotations

import json
from base64 import b64encode

import pytest
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext

from gateway.app import create_app

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture
async def auth_redis(fake_redis):
    """fakeredis with auth enabled."""
    password_hash = pwd_context.hash("secret123")
    await fake_redis.set(
        "config:auth",
        json.dumps(
            {
                "enabled": True,
                "username": "admin",
                "password_hash": password_hash,
            }
        ),
    )
    return fake_redis


@pytest.fixture
async def auth_client(auth_redis):
    """Client with auth-enabled app."""
    application = create_app()
    application.state.redis = auth_redis
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _basic_auth_header(username: str, password: str) -> dict[str, str]:
    """Build HTTP Basic Auth header."""
    cred = b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {cred}"}


@pytest.mark.asyncio
async def test_auth_disabled_allows_access(client: AsyncClient):
    """When auth is disabled, requests without credentials succeed."""
    resp = await client.get("/api/sources")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_enabled_no_credentials(auth_client: AsyncClient):
    """When auth is enabled, request without credentials returns 401."""
    resp = await auth_client.get("/api/sources")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_enabled_valid_credentials(auth_client: AsyncClient):
    """When auth is enabled, valid credentials succeed."""
    resp = await auth_client.get(
        "/api/sources",
        headers=_basic_auth_header("admin", "secret123"),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_enabled_wrong_password(auth_client: AsyncClient):
    """When auth is enabled, wrong password returns 401."""
    resp = await auth_client.get(
        "/api/sources",
        headers=_basic_auth_header("admin", "wrong"),
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_enabled_wrong_username(auth_client: AsyncClient):
    """When auth is enabled, wrong username returns 401."""
    resp = await auth_client.get(
        "/api/sources",
        headers=_basic_auth_header("hacker", "secret123"),
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_health_does_not_require_auth(auth_client: AsyncClient):
    """Health endpoint bypasses auth even when auth is enabled."""
    resp = await auth_client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_env_fallback(fake_redis):
    """When no config:auth in Redis, falls back to env vars."""
    import os

    # Clear any existing auth config
    await fake_redis.delete("config:auth")

    password_hash = pwd_context.hash("envpass")
    os.environ["AUTH_ENABLED"] = "true"
    os.environ["AUTH_USERNAME"] = "envuser"
    os.environ["AUTH_PASSWORD_HASH"] = password_hash

    try:
        application = create_app()
        application.state.redis = fake_redis
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # No creds → 401
            resp = await c.get("/api/sources")
            assert resp.status_code == 401

            # Valid env creds → 200
            resp = await c.get(
                "/api/sources",
                headers=_basic_auth_header("envuser", "envpass"),
            )
            assert resp.status_code == 200
    finally:
        del os.environ["AUTH_ENABLED"]
        del os.environ["AUTH_USERNAME"]
        del os.environ["AUTH_PASSWORD_HASH"]
