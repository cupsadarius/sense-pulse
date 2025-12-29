"""
Data sources package for sense-pulse.

This package provides a unified interface for all data sources (sensors, APIs, system stats).
Each data source implements the DataSource interface and fetches fresh data when polled.
"""

from .aranet4_source import Aranet4DataSource
from .base import DataSource, DataSourceMetadata, SensorReading
from .pihole_source import PiHoleDataSource
from .registry import DataSourceRegistry
from .sensehat_source import SenseHatDataSource
from .system_source import SystemStatsDataSource
from .tailscale_source import TailscaleDataSource

__all__ = [
    "DataSource",
    "DataSourceMetadata",
    "SensorReading",
    "DataSourceRegistry",
    "PiHoleDataSource",
    "TailscaleDataSource",
    "SystemStatsDataSource",
    "Aranet4DataSource",
    "SenseHatDataSource",
]
