"""Data source registry for managing all data sources"""

import logging
from typing import Optional

from .base import DataSource

logger = logging.getLogger(__name__)


class DataSourceRegistry:
    """
    Registry for managing data sources.

    Provides a central place to register, access, and manage all data sources.
    """

    def __init__(self):
        """Initialize empty registry"""
        self._sources: dict[str, DataSource] = {}

    def register(self, source: DataSource) -> None:
        """
        Register a data source.

        Args:
            source: The data source to register

        Raises:
            ValueError: If a source with the same ID is already registered
        """
        metadata = source.get_metadata()
        source_id = metadata.source_id

        if source_id in self._sources:
            raise ValueError(f"Data source '{source_id}' is already registered")

        self._sources[source_id] = source
        logger.info(f"Registered data source: {metadata.name} (id={source_id})")

    def unregister(self, source_id: str) -> None:
        """
        Unregister a data source.

        Args:
            source_id: ID of the source to unregister
        """
        if source_id in self._sources:
            del self._sources[source_id]
            logger.info(f"Unregistered data source: {source_id}")
        else:
            logger.warning(f"Attempted to unregister unknown source: {source_id}")

    def get(self, source_id: str) -> Optional[DataSource]:
        """
        Get a data source by ID.

        Args:
            source_id: ID of the source to retrieve

        Returns:
            The data source, or None if not found
        """
        return self._sources.get(source_id)

    def get_all(self) -> list[DataSource]:
        """
        Get all registered data sources.

        Returns:
            List of all data sources
        """
        return list(self._sources.values())

    def get_enabled(self) -> list[DataSource]:
        """
        Get all enabled data sources.

        Returns:
            List of enabled data sources
        """
        return [
            source
            for source in self._sources.values()
            if source.get_metadata().enabled
        ]

    async def initialize_all(self) -> None:
        """Initialize all registered data sources"""
        logger.info(f"Initializing {len(self._sources)} data source(s)...")

        for source_id, source in self._sources.items():
            try:
                await source.initialize()
            except Exception as e:
                logger.error(f"Error initializing data source '{source_id}': {e}")

    async def shutdown_all(self) -> None:
        """Shutdown all registered data sources"""
        logger.info(f"Shutting down {len(self._sources)} data source(s)...")

        for source_id, source in self._sources.items():
            try:
                await source.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down data source '{source_id}': {e}")

    def __len__(self) -> int:
        """Return number of registered sources"""
        return len(self._sources)

    def __contains__(self, source_id: str) -> bool:
        """Check if a source is registered"""
        return source_id in self._sources
