"""WebSocket-based log handler for streaming logs to web clients."""

import asyncio
import json
import logging
import traceback
from collections import deque
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import WebSocket

# =============================================================================
# Structured Logging Helpers
# =============================================================================


class StructuredLoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter that supports structured logging with extra fields.

    Usage:
        logger = get_structured_logger(__name__)
        logger.info("User logged in", user_id=123, ip="192.168.1.1")
        logger.error("Request failed", status_code=500, path="/api/data")
    """

    def process(
        self, msg: str, kwargs: MutableMapping[str, Any]
    ) -> tuple[str, MutableMapping[str, Any]]:
        """Process log message and extract extra fields."""
        # Extract any extra kwargs that aren't standard logging kwargs
        standard_kwargs = {"exc_info", "stack_info", "stacklevel", "extra"}
        extra = kwargs.pop("extra", {})

        # Move non-standard kwargs to extra
        for key in list(kwargs.keys()):
            if key not in standard_kwargs:
                extra[key] = kwargs.pop(key)

        # Merge with adapter's extra
        if self.extra:
            extra = {**self.extra, **extra}

        kwargs["extra"] = extra
        return msg, kwargs


def get_structured_logger(name: str, **default_extra: Any) -> StructuredLoggerAdapter:
    """
    Get a structured logger that supports extra keyword arguments.

    Args:
        name: Logger name (usually __name__)
        **default_extra: Default extra fields to include in all logs

    Returns:
        A StructuredLoggerAdapter instance

    Example:
        logger = get_structured_logger(__name__, component="cache")
        logger.info("Cache hit", key="user_123", age_seconds=5.2)
    """
    base_logger = logging.getLogger(name)
    return StructuredLoggerAdapter(base_logger, default_extra)


@dataclass
class LogEntry:
    """Represents a single log entry."""

    timestamp: float
    level: str
    level_num: int
    logger_name: str
    message: str
    module: str
    funcName: str
    lineno: int
    exc_info: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "level_num": self.level_num,
            "logger": self.logger_name,
            "message": self.message,
            "module": self.module,
            "function": self.funcName,
            "line": self.lineno,
            "exc_info": self.exc_info,
            "extra": self.extra if self.extra else None,
        }


class WebSocketLogHandler(logging.Handler):
    """
    A logging handler that broadcasts log records to connected WebSocket clients.

    This handler maintains a buffer of recent logs and broadcasts new logs
    to all connected clients in real-time.
    """

    def __init__(
        self,
        level: int = logging.DEBUG,
        buffer_size: int = 500,
    ):
        """
        Initialize the WebSocket log handler.

        Args:
            level: Minimum log level to capture
            buffer_size: Maximum number of logs to keep in buffer
        """
        super().__init__(level)
        self._clients: set[WebSocket] = set()
        self._buffer: deque[LogEntry] = deque(maxlen=buffer_size)
        self._lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Set a simple formatter
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record to all connected WebSocket clients.

        This method is called by the logging framework for each log record.
        """
        try:
            # Create log entry
            entry = self._create_log_entry(record)

            # Add to buffer
            self._buffer.append(entry)

            # Broadcast to clients if we have any
            if self._clients and self._loop:
                # Schedule the broadcast in the event loop
                asyncio.run_coroutine_threadsafe(self._broadcast_log(entry), self._loop)
        except Exception:
            self.handleError(record)

    def _create_log_entry(self, record: logging.LogRecord) -> LogEntry:
        """Create a LogEntry from a LogRecord."""
        exc_info = None
        if record.exc_info:
            exc_info = "".join(traceback.format_exception(*record.exc_info))

        # Extract any extra fields that were added to the log record
        extra = {}
        standard_attrs = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "asctime",
            "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs:
                try:
                    # Ensure the value is JSON serializable
                    json.dumps(value)
                    extra[key] = value
                except (TypeError, ValueError):
                    extra[key] = str(value)

        return LogEntry(
            timestamp=record.created,
            level=record.levelname,
            level_num=record.levelno,
            logger_name=record.name,
            message=record.getMessage(),
            module=record.module,
            funcName=record.funcName,
            lineno=record.lineno,
            exc_info=exc_info,
            extra=extra,
        )

    async def _broadcast_log(self, entry: LogEntry) -> None:
        """Broadcast a log entry to all connected clients."""
        if not self._clients:
            return

        message = json.dumps({"type": "log", "data": entry.to_dict()})

        # Send to all clients, removing any that fail
        disconnected = set()
        for client in self._clients:
            try:
                await client.send_text(message)
            except Exception:
                disconnected.add(client)

        # Remove disconnected clients
        self._clients -= disconnected

    async def register_client(self, websocket: WebSocket) -> None:
        """
        Register a new WebSocket client.

        Args:
            websocket: The WebSocket connection to register
        """
        async with self._lock:
            self._clients.add(websocket)
            # Store the event loop for broadcasting from sync context
            self._loop = asyncio.get_event_loop()

    async def unregister_client(self, websocket: WebSocket) -> None:
        """
        Unregister a WebSocket client.

        Args:
            websocket: The WebSocket connection to unregister
        """
        async with self._lock:
            self._clients.discard(websocket)

    def get_buffer(self, min_level: int = logging.DEBUG) -> list[dict[str, Any]]:
        """
        Get buffered logs filtered by minimum level.

        Args:
            min_level: Minimum log level to include

        Returns:
            List of log entries as dictionaries
        """
        return [entry.to_dict() for entry in self._buffer if entry.level_num >= min_level]

    @property
    def client_count(self) -> int:
        """Return the number of connected clients."""
        return len(self._clients)


# Global handler instance
_log_handler: Optional[WebSocketLogHandler] = None


def get_log_handler() -> WebSocketLogHandler:
    """Get or create the global WebSocket log handler."""
    global _log_handler
    if _log_handler is None:
        _log_handler = WebSocketLogHandler(level=logging.DEBUG)
    return _log_handler


def setup_websocket_logging() -> WebSocketLogHandler:
    """
    Get or create the WebSocket log handler.

    The handler should be added to logging.basicConfig() handlers list
    during app initialization to capture all logs from startup.

    Returns:
        The WebSocket log handler (singleton)
    """
    return get_log_handler()
