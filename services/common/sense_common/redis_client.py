"""Redis client utilities for Sense Pulse microservices."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as aioredis
from sense_common.models import (
    Command,
    CommandResponse,
    SensorReading,
    SourceMetadata,
    SourceStatus,
)

logger = logging.getLogger(__name__)

# Default TTLs
DATA_TTL = 60  # seconds
STATUS_TTL = 120  # seconds


async def create_redis(url: str, max_retries: int = 3, retry_delay: float = 1.0) -> aioredis.Redis:
    """Create a Redis connection with retry logic."""
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            client = aioredis.from_url(url, decode_responses=True)
            await client.ping()
            logger.info("Connected to Redis at %s", url)
            return client  # type: ignore[no-any-return]
        except (aioredis.ConnectionError, OSError) as e:
            last_error = e
            if attempt < max_retries - 1:
                logger.warning(
                    "Redis connection attempt %d/%d failed: %s. Retrying in %.1fs...",
                    attempt + 1,
                    max_retries,
                    e,
                    retry_delay,
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # exponential backoff
    raise ConnectionError(f"Failed to connect to Redis after {max_retries} attempts: {last_error}")


# --- Source Data ---


async def write_readings(
    redis: aioredis.Redis,
    source_id: str,
    readings: list[SensorReading],
    ttl: int = DATA_TTL,
) -> None:
    """Write sensor readings to Redis with TTL."""
    pipe = redis.pipeline()
    for r in readings:
        key = f"source:{source_id}:{r.sensor_id}"
        value = json.dumps({"value": r.value, "unit": r.unit, "timestamp": r.timestamp})
        pipe.set(key, value, ex=ttl)
    await pipe.execute()


async def read_source(redis: aioredis.Redis, source_id: str) -> dict[str, Any]:
    """Read all readings for a single source."""
    readings: dict[str, Any] = {}
    cursor = 0
    pattern = f"source:{source_id}:*"
    prefix = f"source:{source_id}:"

    while True:
        cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=100)
        if keys:
            values = await redis.mget(keys)
            for key, val in zip(keys, values, strict=False):
                if val is not None:
                    sensor_id = key[len(prefix) :]
                    readings[sensor_id] = json.loads(val)
        if cursor == 0:
            break

    return readings


async def read_all_sources(redis: aioredis.Redis) -> dict[str, dict[str, Any]]:
    """Read all source readings, grouped by source_id."""
    sources: dict[str, dict[str, Any]] = {}
    cursor = 0

    while True:
        cursor, keys = await redis.scan(cursor=cursor, match="source:*", count=100)
        if keys:
            values = await redis.mget(keys)
            for key, val in zip(keys, values, strict=False):
                if val is not None:
                    # key format: source:{source_id}:{sensor_id}
                    parts = key.split(":", 2)
                    if len(parts) == 3:
                        _, source_id, sensor_id = parts
                        if source_id not in sources:
                            sources[source_id] = {}
                        sources[source_id][sensor_id] = json.loads(val)
        if cursor == 0:
            break

    return sources


# --- Source Metadata ---


async def write_metadata(redis: aioredis.Redis, source_id: str, metadata: SourceMetadata) -> None:
    """Write source metadata (no TTL)."""
    key = f"meta:{source_id}"
    await redis.set(key, metadata.model_dump_json())


async def read_metadata(redis: aioredis.Redis, source_id: str) -> SourceMetadata | None:
    """Read source metadata."""
    val = await redis.get(f"meta:{source_id}")
    if val is None:
        return None
    return SourceMetadata.model_validate_json(val)


# --- Source Status ---


async def write_status(
    redis: aioredis.Redis,
    source_id: str,
    status: SourceStatus,
    ttl: int = STATUS_TTL,
) -> None:
    """Write source status with TTL."""
    key = f"status:{source_id}"
    await redis.set(key, status.model_dump_json(), ex=ttl)


async def read_status(redis: aioredis.Redis, source_id: str) -> SourceStatus | None:
    """Read a single source status."""
    val = await redis.get(f"status:{source_id}")
    if val is None:
        return None
    return SourceStatus.model_validate_json(val)


async def read_all_statuses(redis: aioredis.Redis) -> list[SourceStatus]:
    """Read all source statuses."""
    statuses: list[SourceStatus] = []
    cursor = 0

    while True:
        cursor, keys = await redis.scan(cursor=cursor, match="status:*", count=100)
        if keys:
            values = await redis.mget(keys)
            for val in values:
                if val is not None:
                    statuses.append(SourceStatus.model_validate_json(val))
        if cursor == 0:
            break

    return statuses


# --- Pub/Sub: Data Updates ---


async def publish_data(redis: aioredis.Redis, source_id: str) -> None:
    """Publish a data update notification."""
    payload = json.dumps({"source_id": source_id, "timestamp": time.time()})
    await redis.publish(f"data:{source_id}", payload)


# --- Pub/Sub: Commands ---


async def publish_command(redis: aioredis.Redis, source_id: str, command: Command) -> None:
    """Publish a command to a service."""
    await redis.publish(f"cmd:{source_id}", command.model_dump_json())


async def subscribe_commands(redis: aioredis.Redis, source_id: str) -> AsyncIterator[Command]:
    """Subscribe to commands for a service. Yields Command objects."""
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"cmd:{source_id}")
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    yield Command.model_validate_json(message["data"])
                except Exception:
                    logger.exception("Failed to parse command: %s", message["data"])
    finally:
        await pubsub.unsubscribe(f"cmd:{source_id}")
        await pubsub.aclose()


# --- Pub/Sub: Command Responses ---


async def publish_response(
    redis: aioredis.Redis, source_id: str, response: CommandResponse
) -> None:
    """Publish a command response."""
    channel = f"cmd:{source_id}:response:{response.request_id}"
    await redis.publish(channel, response.model_dump_json())


async def wait_response(
    redis: aioredis.Redis,
    source_id: str,
    request_id: str,
    timeout: float = 5.0,
) -> CommandResponse | None:
    """Wait for a command response with timeout."""
    channel = f"cmd:{source_id}:response:{request_id}"
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is not None and message["type"] == "message":
                try:
                    return CommandResponse.model_validate_json(message["data"])
                except Exception:
                    logger.exception("Failed to parse response: %s", message["data"])
                    return None
        logger.warning("Timeout waiting for response on %s", channel)
        return None
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()


# --- Config ---


async def read_config(redis: aioredis.Redis, section: str) -> dict[str, Any] | None:
    """Read a config section from Redis."""
    val = await redis.get(f"config:{section}")
    if val is None:
        return None
    return dict(json.loads(val))


async def write_config(redis: aioredis.Redis, section: str, data: dict[str, Any]) -> None:
    """Write a config section to Redis (no TTL)."""
    await redis.set(f"config:{section}", json.dumps(data))


async def seed_config_from_env(redis: aioredis.Redis, section: str, data: dict[str, Any]) -> bool:
    """Seed a config section using SET NX (only if key doesn't exist). Returns True if written."""
    return bool(await redis.set(f"config:{section}", json.dumps(data), nx=True))


# --- Pub/Sub: Config Changes ---


async def subscribe_config_changes(redis: aioredis.Redis) -> AsyncIterator[str]:
    """Subscribe to config change notifications. Yields section names."""
    pubsub = redis.pubsub()
    await pubsub.subscribe("config:changed")
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    payload = json.loads(message["data"])
                    yield payload["section"]
                except Exception:
                    logger.exception("Failed to parse config change: %s", message["data"])
    finally:
        await pubsub.unsubscribe("config:changed")
        await pubsub.aclose()


async def publish_config_changed(redis: aioredis.Redis, section: str) -> None:
    """Publish a config change notification."""
    payload = json.dumps({"section": section, "timestamp": time.time()})
    await redis.publish("config:changed", payload)
