"""Pi-hole v6 API statistics fetching"""

import logging
from typing import Optional

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


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
        logger.info(f"Initialized Pi-hole stats fetcher for: {self.host}")

    @retry(
        retry=retry_if_exception_type(
            (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _authenticate(self) -> bool:
        """Authenticate with Pi-hole and get session ID (with retries)"""
        if not self.password:
            logger.debug("No password configured, trying unauthenticated access")
            return True

        try:
            response = requests.post(
                f"{self.host}/api/auth",
                json={"password": self.password},
                timeout=5,
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

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            logger.warning(f"Pi-hole authentication connection error (will retry): {e}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Pi-hole authentication failed: {e}")
            return False

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with session ID if authenticated"""
        headers = {}
        if self._session_id:
            headers["sid"] = self._session_id
        return headers

    @retry(
        retry=retry_if_exception_type(
            (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def fetch_stats(self) -> Optional[dict]:
        """Fetch current Pi-hole stats from API (with retries)"""
        # Try to authenticate if we have a password and no session
        if self.password and not self._session_id and not self._authenticate():
            return None

        try:
            logger.debug("Fetching Pi-hole stats...")
            response = requests.get(
                f"{self.host}/api/stats/summary",
                headers=self._get_headers(),
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()
            logger.debug("Successfully fetched Pi-hole stats")
            return data

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                # Session expired, try to re-authenticate
                logger.debug("Session expired, re-authenticating...")
                self._session_id = None
                if self._authenticate():
                    return self.fetch_stats()
            logger.error(f"Failed to fetch Pi-hole stats: {e}")
            return None
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            logger.warning(f"Pi-hole stats connection error (will retry): {e}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch Pi-hole stats: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching Pi-hole stats: {e}")
            return None

    def get_summary(self) -> dict[str, float]:
        """Get summarized Pi-hole stats"""
        stats = self.fetch_stats()
        if not stats:
            logger.warning("No Pi-hole stats available, returning defaults")
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
