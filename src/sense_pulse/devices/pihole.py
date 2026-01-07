"""Pi-hole v6 API statistics fetching"""

from typing import Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..web.log_handler import get_structured_logger

logger = get_structured_logger(__name__, component="pihole")


class PiHoleStats:
    """Handles fetching Pi-hole v6 statistics"""

    def __init__(self, host: str, password: str = ""):
        """
        Initialize Pi-hole stats fetcher.

        Args:
            host: Pi-hole host URL (e.g., http://localhost)
            password: App password from Pi-hole settings
        """
        self.host = host.rstrip("/")
        self.password = password
        self._session_id: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None
        logger.info("Initialized Pi-hole stats fetcher", host=self.host)

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is initialized"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=5.0)
        return self._client

    async def close(self) -> None:
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _authenticate(self) -> bool:
        """Authenticate with Pi-hole and get session ID (with retries)"""
        if not self.password:
            logger.debug("No password configured, trying unauthenticated access")
            return True

        try:
            client = await self._ensure_client()
            response = await client.post(
                f"{self.host}/api/auth",
                json={"password": self.password},
            )
            response.raise_for_status()
            data = response.json()

            if data.get("session", {}).get("valid"):
                self._session_id = data["session"].get("sid")
                logger.debug("Successfully authenticated with Pi-hole")
                return True
            else:
                logger.error("Pi-hole authentication failed: invalid credentials")
                return False

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.warning(
                "Pi-hole authentication connection error (will retry)",
                host=self.host,
                error=str(e),
            )
            raise
        except httpx.HTTPStatusError as e:
            logger.error("Pi-hole authentication failed", host=self.host, error=str(e))
            return False

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with session ID if authenticated"""
        headers = {}
        if self._session_id:
            headers["sid"] = self._session_id
        return headers

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def fetch_stats(self) -> Optional[dict]:
        """Fetch current Pi-hole stats from API (with retries)"""
        # Try to authenticate if we have a password and no session
        if self.password and not self._session_id and not await self._authenticate():
            return None

        try:
            logger.debug("Fetching Pi-hole stats", host=self.host)
            client = await self._ensure_client()
            response = await client.get(
                f"{self.host}/api/stats/summary",
                headers=self._get_headers(),
            )
            response.raise_for_status()
            data = response.json()
            logger.debug("Successfully fetched Pi-hole stats", host=self.host)
            return data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Session expired, try to re-authenticate
                logger.debug("Session expired, re-authenticating", host=self.host)
                self._session_id = None
                if await self._authenticate():
                    return await self.fetch_stats()
            logger.error("Failed to fetch Pi-hole stats", host=self.host, error=str(e))
            return None
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.warning(
                "Pi-hole stats connection error (will retry)",
                host=self.host,
                error=str(e),
            )
            raise
        except httpx.HTTPError as e:
            logger.error("Failed to fetch Pi-hole stats", host=self.host, error=str(e))
            return None
        except Exception as e:
            logger.error("Unexpected error fetching Pi-hole stats", host=self.host, error=str(e))
            return None

    async def get_summary(self) -> dict[str, float]:
        """Get summarized Pi-hole stats"""
        stats = await self.fetch_stats()
        if not stats:
            logger.warning("No Pi-hole stats available, returning defaults", host=self.host)
            return {
                "queries_today": 0,
                "ads_blocked_today": 0,
                "ads_percentage_today": 0.0,
            }

        # Pi-hole v6 API response structure
        queries = stats.get("queries", {})
        return {
            "queries_today": queries.get("total", 0),
            "ads_blocked_today": queries.get("blocked", 0),
            "ads_percentage_today": queries.get("percent_blocked", 0.0),
        }
