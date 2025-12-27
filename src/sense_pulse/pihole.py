"""Pi-hole statistics fetching"""

import logging
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)


class PiHoleStats:
    """Handles fetching Pi-hole statistics"""

    def __init__(self, api_url: str):
        """
        Initialize Pi-hole stats fetcher.

        Args:
            api_url: Pi-hole API endpoint URL
        """
        self.api_url = api_url
        logger.info(f"Initialized Pi-hole stats fetcher with URL: {api_url}")

    def fetch_stats(self) -> Optional[Dict]:
        """Fetch current Pi-hole stats from API"""
        try:
            logger.debug("Fetching Pi-hole stats...")
            response = requests.get(self.api_url, timeout=5)
            response.raise_for_status()
            data = response.json()
            logger.debug(f"Successfully fetched Pi-hole stats: {list(data.keys())}")
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch Pi-hole stats: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching Pi-hole stats: {e}")
            return None

    def get_summary(self) -> Dict[str, float]:
        """Get summarized Pi-hole stats"""
        stats = self.fetch_stats()
        if not stats:
            logger.warning("No Pi-hole stats available, returning defaults")
            return {
                "queries_today": 0,
                "ads_blocked_today": 0,
                "ads_percentage_today": 0.0,
            }

        return {
            "queries_today": stats.get("dns_queries_today", 0),
            "ads_blocked_today": stats.get("ads_blocked_today", 0),
            "ads_percentage_today": stats.get("ads_percentage_today", 0.0),
        }
