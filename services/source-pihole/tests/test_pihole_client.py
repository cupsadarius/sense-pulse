"""Tests for Pi-hole HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from pihole.client import PiHoleClient


@pytest.fixture
def client() -> PiHoleClient:
    return PiHoleClient("http://pihole.local", "secret")


@pytest.fixture
def no_auth_client() -> PiHoleClient:
    return PiHoleClient("http://pihole.local", "")


class TestAuthentication:
    async def test_authenticate_success(self, client: PiHoleClient) -> None:
        """Successful authentication stores session ID."""
        http = AsyncMock()
        http.post = AsyncMock(
            return_value=httpx.Response(
                200,
                json={"session": {"valid": True, "sid": "abc123"}},
                request=httpx.Request("POST", "http://pihole.local/api/auth"),
            )
        )
        result = await client.authenticate(http)
        assert result is True
        assert client._session_id == "abc123"

    async def test_authenticate_invalid_credentials(self, client: PiHoleClient) -> None:
        """Invalid credentials return False."""
        http = AsyncMock()
        http.post = AsyncMock(
            return_value=httpx.Response(
                200,
                json={"session": {"valid": False}},
                request=httpx.Request("POST", "http://pihole.local/api/auth"),
            )
        )
        result = await client.authenticate(http)
        assert result is False
        assert client._session_id is None

    async def test_no_password_skips_auth(self, no_auth_client: PiHoleClient) -> None:
        """No password returns True without making a request."""
        http = AsyncMock()
        result = await no_auth_client.authenticate(http)
        assert result is True
        http.post.assert_not_called()

    async def test_host_trailing_slash_stripped(self) -> None:
        """Trailing slash on host is removed."""
        c = PiHoleClient("http://pihole.local/", "pass")
        assert c.host == "http://pihole.local"


class TestFetchStats:
    async def test_fetch_stats_success(self, client: PiHoleClient) -> None:
        """Successful stats fetch after authentication."""
        http = AsyncMock()
        http.post = AsyncMock(
            return_value=httpx.Response(
                200,
                json={"session": {"valid": True, "sid": "abc123"}},
                request=httpx.Request("POST", "http://pihole.local/api/auth"),
            )
        )
        http.get = AsyncMock(
            return_value=httpx.Response(
                200,
                json={"queries": {"total": 100, "blocked": 10, "percent_blocked": 10.0}},
                request=httpx.Request("GET", "http://pihole.local/api/stats/summary"),
            )
        )
        stats = await client.fetch_stats(http)
        assert stats is not None
        assert stats["queries"]["total"] == 100

    async def test_fetch_stats_no_password(self, no_auth_client: PiHoleClient) -> None:
        """Stats fetch without password (no auth needed)."""
        http = AsyncMock()
        http.get = AsyncMock(
            return_value=httpx.Response(
                200,
                json={"queries": {"total": 50}},
                request=httpx.Request("GET", "http://pihole.local/api/stats/summary"),
            )
        )
        stats = await no_auth_client.fetch_stats(http)
        assert stats is not None
        assert stats["queries"]["total"] == 50
        http.post.assert_not_called()

    async def test_fetch_stats_auth_failure_returns_none(self, client: PiHoleClient) -> None:
        """Failed authentication causes fetch_stats to return None."""
        http = AsyncMock()
        http.post = AsyncMock(
            return_value=httpx.Response(
                200,
                json={"session": {"valid": False}},
                request=httpx.Request("POST", "http://pihole.local/api/auth"),
            )
        )
        stats = await client.fetch_stats(http)
        assert stats is None

    async def test_session_id_sent_in_headers(self, client: PiHoleClient) -> None:
        """Session ID is included in request headers."""
        client._session_id = "existing-sid"
        http = AsyncMock()
        http.get = AsyncMock(
            return_value=httpx.Response(
                200,
                json={"queries": {}},
                request=httpx.Request("GET", "http://pihole.local/api/stats/summary"),
            )
        )
        await client.fetch_stats(http)
        http.get.assert_called_once()
        call_kwargs = http.get.call_args
        assert call_kwargs.kwargs["headers"]["sid"] == "existing-sid"
