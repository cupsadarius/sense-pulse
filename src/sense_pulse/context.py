"""
Application context for dependency injection.

This module provides a central container for all application dependencies,
eliminating the need for global singletons and enabling clean testing.

Usage:
    config = load_config()
    context = AppContext.create(config)
    context.add_data_source(TailscaleDataSource(config.tailscale))
    context.add_data_source(PiHoleDataSource(config.pihole))
    await context.start()

    # Pass context to components
    controller = StatsDisplay(context.config, cache=context.cache)
    app = create_app(context=context)

    # On shutdown
    await context.shutdown()
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sense_hat import SenseHat

    from sense_pulse.datasources.base import DataSource

from sense_pulse.cache import DataCache
from sense_pulse.config import Config

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """
    Application context containing all shared dependencies.

    This class owns the lifecycle of all major components:
    - Configuration
    - Data cache
    - Data sources
    - Shared hardware instances (e.g., SenseHat)

    Attributes:
        config: Application configuration loaded from YAML
        cache: DataCache instance for caching sensor readings
        data_sources: List of registered DataSource instances
        sense_hat: Optional shared SenseHat hardware instance
    """

    config: Config
    cache: DataCache
    data_sources: list["DataSource"] = field(default_factory=list)
    sense_hat: Optional["SenseHat"] = None
    _started: bool = field(default=False, repr=False)

    @classmethod
    def create(
        cls,
        config: Config,
        cache_ttl: float = 60.0,
        poll_interval: float = 30.0,
    ) -> "AppContext":
        """
        Factory method to create AppContext with configured cache.

        Args:
            config: Application configuration
            cache_ttl: Cache time-to-live in seconds (default: 60)
            poll_interval: Background poll interval in seconds (default: 30)

        Returns:
            Configured AppContext instance ready for data source registration

        Example:
            context = AppContext.create(load_config())
            context.add_data_source(MyDataSource())
            await context.start()
        """
        cache = DataCache(cache_ttl=cache_ttl, poll_interval=poll_interval)
        logger.debug(f"Created AppContext with cache TTL={cache_ttl}s, poll={poll_interval}s")
        return cls(config=config, cache=cache)

    def add_data_source(self, source: "DataSource") -> "AppContext":
        """
        Add a data source to the context.

        Args:
            source: DataSource instance to add

        Returns:
            self (for method chaining)

        Example:
            context.add_data_source(source1).add_data_source(source2)
        """
        self.data_sources.append(source)
        metadata = source.get_metadata()
        logger.debug(f"Added data source: {metadata.name} (id={metadata.source_id})")
        return self

    async def start(self) -> None:
        """
        Initialize all data sources and start cache polling.

        This method:
        1. Initializes each registered data source
        2. Registers sources with the cache
        3. Starts background polling

        Raises:
            RuntimeError: If context is already started

        Note:
            If a data source fails to initialize, it is logged but other
            sources continue to be initialized.
        """
        if self._started:
            logger.warning("AppContext already started, ignoring start() call")
            return

        logger.info(f"Starting AppContext with {len(self.data_sources)} data source(s)...")

        # Initialize all data sources
        initialized_count = 0
        for source in self.data_sources:
            metadata = source.get_metadata()
            try:
                await source.initialize()
                self.cache.register_data_source(source)
                initialized_count += 1
                logger.info(f"✓ Initialized: {metadata.name}")
            except Exception as e:
                logger.error(f"✗ Failed to initialize {metadata.name}: {e}")

        # Start background polling
        await self.cache.start_polling()
        self._started = True

        logger.info(
            f"AppContext started: {initialized_count}/{len(self.data_sources)} sources initialized"
        )

    async def shutdown(self) -> None:
        """
        Clean shutdown of all components.

        This method:
        1. Stops cache polling
        2. Shuts down all data sources

        Safe to call multiple times or before start().
        """
        if not self._started:
            logger.debug("AppContext not started, nothing to shutdown")
            return

        logger.info("Shutting down AppContext...")

        # Stop polling first
        await self.cache.stop_polling()

        # Shutdown all data sources
        shutdown_count = 0
        for source in self.data_sources:
            metadata = source.get_metadata()
            try:
                await source.shutdown()
                shutdown_count += 1
                logger.debug(f"✓ Shutdown: {metadata.name}")
            except Exception as e:
                logger.error(f"✗ Error shutting down {metadata.name}: {e}")

        self._started = False
        logger.info(f"AppContext shutdown complete ({shutdown_count} sources)")

    @property
    def is_started(self) -> bool:
        """Check if context has been started."""
        return self._started

    def get_data_source(self, source_id: str) -> Optional["DataSource"]:
        """
        Get a data source by ID.

        Args:
            source_id: The source identifier to find

        Returns:
            The DataSource if found, None otherwise
        """
        for source in self.data_sources:
            if source.get_metadata().source_id == source_id:
                return source
        return None

    def __repr__(self) -> str:
        sources = [s.get_metadata().source_id for s in self.data_sources]
        return (
            f"AppContext(started={self._started}, "
            f"sources={sources}, "
            f"cache_ttl={self.cache.cache_ttl})"
        )
