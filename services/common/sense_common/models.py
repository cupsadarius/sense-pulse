"""Pydantic models for inter-service communication."""

from __future__ import annotations

import time
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class SensorReading(BaseModel):
    """A single scalar sensor reading."""

    sensor_id: str
    value: int | float | str | bool
    unit: str | None = None
    timestamp: float = Field(default_factory=time.time)


class SourceMetadata(BaseModel):
    """Metadata describing a data source."""

    source_id: str
    name: str
    description: str
    refresh_interval: int  # seconds
    enabled: bool = True


class SourceStatus(BaseModel):
    """Health/status information for a data source."""

    source_id: str
    last_poll: float | None = None
    last_success: float | None = None
    last_error: str | None = None
    poll_count: int = 0
    error_count: int = 0


class Command(BaseModel):
    """A command sent to a service via Redis pub/sub."""

    action: str
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    params: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class CommandResponse(BaseModel):
    """Response to a command."""

    request_id: str
    status: Literal["ok", "error"]
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
