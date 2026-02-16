"""Pi-hole v6 API client."""

from __future__ import annotations

import logging

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


class PiHoleClient:
    """Async HTTP client for Pi-hole v6 API."""

    def __init__(self, host: str, password: str = "") -> None:
        self.host = host.rstrip("/")
        self.password = password
        self._session_id: str | None = None

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def authenticate(self, client: httpx.AsyncClient) -> bool:
        """Authenticate with Pi-hole and obtain a session ID."""
        if not self.password:
            logger.debug("No password configured, trying unauthenticated access")
            return True

        try:
            response = await client.post(
                f"{self.host}/api/auth",
                json={"password": self.password},
            )
            response.raise_for_status()
            data = response.json()

            if data.get("session", {}).get("valid"):
                self._session_id = data["session"].get("sid")
                logger.debug("Authenticated with Pi-hole")
                return True

            logger.error("Pi-hole authentication failed: invalid credentials")
            return False

        except (httpx.ConnectError, httpx.TimeoutException):
            raise
        except httpx.HTTPStatusError as e:
            logger.error("Pi-hole auth HTTP error: %s", e)
            return False

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def fetch_stats(self, client: httpx.AsyncClient) -> dict | None:
        """Fetch Pi-hole summary stats. Returns None on failure."""
        # Authenticate if needed
        if self.password and not self._session_id:
            if not await self.authenticate(client):
                return None

        headers: dict[str, str] = {}
        if self._session_id:
            headers["sid"] = self._session_id

        try:
            response = await client.get(
                f"{self.host}/api/stats/summary",
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.debug("Session expired, re-authenticating")
                self._session_id = None
                if await self.authenticate(client):
                    return await self.fetch_stats(client)
            logger.error("Pi-hole stats HTTP error: %s", e)
            return None
        except (httpx.ConnectError, httpx.TimeoutException):
            raise
        except httpx.HTTPError as e:
            logger.error("Pi-hole stats error: %s", e)
            return None
