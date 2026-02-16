# Sense Pulse - Shared API Contract

> **Purpose:** Single source of truth for inter-service communication.
> Every agent MUST read this before implementing their service.
> Do NOT modify this file -- it is owned by Phase 1 (foundation).

---

## Table of Contents

1. [Redis Key Schema](#redis-key-schema)
2. [Redis Config Keys](#redis-config-keys)
3. [Pub/Sub Channels](#pubsub-channels)
4. [Service Environment Variables](#service-environment-variables)
5. [Common Library Exports](#common-library-exports-sense-common)
6. [Config Read Pattern](#config-read-pattern)
7. [Gateway API Endpoints](#gateway-api-endpoints)

---

## Redis Key Schema

### Source Data Keys

**Pattern:** `source:{source_id}:{sensor_id}`
**Type:** String (JSON)
**TTL:** 60 seconds (set by writing service)

```json
{"value": "<scalar>", "unit": "<string|null>", "timestamp": 1708000000.0}
```

**Value constraint:** `value` MUST be a scalar: `int`, `float`, `str`, or `bool`.
No dicts, no lists. Complex data is flattened into multiple readings.

#### Tailscale (`source_id: "tailscale"`)

| sensor_id      | value type | unit      | example |
|----------------|-----------|-----------|---------|
| `connected`    | bool      | --        | `true`  |
| `device_count` | int       | "devices" | `5`     |

#### Pi-hole (`source_id: "pihole"`)

| sensor_id              | value type | unit      | example  |
|------------------------|-----------|-----------|----------|
| `queries_today`        | int       | "queries" | `12345`  |
| `ads_blocked_today`    | int       | "ads"     | `1234`   |
| `ads_percentage_today` | float     | "%"       | `10.0`   |

#### System (`source_id: "system"`)

| sensor_id        | value type | unit   | example |
|------------------|-----------|--------|---------|
| `cpu_percent`    | float     | "%"    | `23.5`  |
| `memory_percent` | float     | "%"    | `61.2`  |
| `load_1min`      | float     | "load" | `1.23`  |
| `cpu_temp`       | float     | "C"    | `52.3`  |

#### Sense HAT Sensors (`source_id: "sensors"`)

| sensor_id     | value type     | unit   | example  |
|---------------|---------------|--------|----------|
| `temperature` | float or null | "C"    | `24.3`   |
| `humidity`    | float or null | "%"    | `45.2`   |
| `pressure`    | float or null | "mbar" | `1013.2` |

#### Aranet4 CO2 (`source_id: "co2"`)

Each physical sensor (configured by label, e.g., "office") produces 5 scalar readings
using a compound `sensor_id` of `{label}:{metric}`:

| sensor_id              | value type | unit   | example  |
|------------------------|-----------|--------|----------|
| `{label}:co2`         | int       | "ppm"  | `450`    |
| `{label}:temperature` | float     | "C"    | `22.1`   |
| `{label}:humidity`    | int       | "%"    | `45`     |
| `{label}:pressure`    | float     | "mbar" | `1013.2` |
| `{label}:battery`     | int       | "%"    | `85`     |

Example Redis keys for a sensor labeled "office":

```
source:co2:office:co2          → {"value": 450, "unit": "ppm", "timestamp": 1708000000.0}
source:co2:office:temperature  → {"value": 22.1, "unit": "C", "timestamp": 1708000000.0}
source:co2:office:humidity     → {"value": 45, "unit": "%", "timestamp": 1708000000.0}
source:co2:office:pressure     → {"value": 1013.2, "unit": "mbar", "timestamp": 1708000000.0}
source:co2:office:battery      → {"value": 85, "unit": "%", "timestamp": 1708000000.0}
```

The gateway can reconstruct a per-sensor grouped view from the flat readings if needed.

#### Weather (`source_id: "weather"`)

**Current conditions (11 readings):**

| sensor_id              | value type | unit    | example           |
|------------------------|-----------|---------|-------------------|
| `weather_temp`         | float     | "C"     | `18.0`            |
| `weather_feels_like`   | float     | "C"     | `16.0`            |
| `weather_humidity`     | int       | "%"     | `72`              |
| `weather_conditions`   | str       | null    | `"Partly cloudy"` |
| `weather_wind`         | float     | "km/h"  | `15.0`            |
| `weather_wind_dir`     | str       | null    | `"SW"`            |
| `weather_pressure`     | float     | "mb"    | `1015.0`          |
| `weather_uv_index`     | int       | null    | `3`               |
| `weather_visibility`   | float     | "km"    | `10.0`            |
| `weather_cloud_cover`  | int       | "%"     | `50`              |
| `weather_location`     | str       | null    | `"London"`        |

**Forecast (15 readings, 3 days x 5 fields):**

| sensor_id                     | value type | unit | example           |
|-------------------------------|-----------|------|-------------------|
| `forecast_d0_date`            | str       | null | `"2026-02-16"`    |
| `forecast_d0_max_temp`        | float     | "C"  | `12.0`            |
| `forecast_d0_min_temp`        | float     | "C"  | `5.0`             |
| `forecast_d0_avg_temp`        | float     | "C"  | `8.5`             |
| `forecast_d0_description`     | str       | null | `"Partly cloudy"` |
| `forecast_d1_date`            | str       | null | `"2026-02-17"`    |
| `forecast_d1_max_temp`        | float     | "C"  | `10.0`            |
| `forecast_d1_min_temp`        | float     | "C"  | `3.0`             |
| `forecast_d1_avg_temp`        | float     | "C"  | `6.5`             |
| `forecast_d1_description`     | str       | null | `"Rain"`          |
| `forecast_d2_date`            | str       | null | `"2026-02-18"`    |
| `forecast_d2_max_temp`        | float     | "C"  | `14.0`            |
| `forecast_d2_min_temp`        | float     | "C"  | `7.0`             |
| `forecast_d2_avg_temp`        | float     | "C"  | `10.5`            |
| `forecast_d2_description`     | str       | null | `"Sunny"`         |

Total: 26 readings per poll. The gateway can reconstruct a forecast array from `forecast_d*` keys if needed.

#### Network Camera (`source_id: "network_camera"`)

| sensor_id           | value type | unit      | example         |
|---------------------|-----------|-----------|-----------------|
| `stream_status`     | str       | null      | `"streaming"`   |
| `stream_connected`  | bool      | null      | `true`          |
| `stream_error`      | str       | null      | `null`          |
| `stream_resolution` | str       | null      | `"1920x1080"`   |
| `stream_fps`        | int       | "fps"     | `25`            |
| `stream_uptime`     | float     | "seconds" | `3600.0`        |

`stream_status` is one of: `"stopped"`, `"starting"`, `"streaming"`, `"reconnecting"`, `"error"`.
`stream_resolution` and `stream_fps` may be absent if the device doesn't report them.

### Source Metadata Keys

**Pattern:** `meta:{source_id}`
**Type:** String (JSON)
**TTL:** None (persists until overwritten)

```json
{
    "source_id": "weather",
    "name": "Weather",
    "description": "Current weather conditions from wttr.in",
    "refresh_interval": 300,
    "enabled": true
}
```

### Source Status Keys

**Pattern:** `status:{source_id}`
**Type:** String (JSON)
**TTL:** 120 seconds

```json
{
    "source_id": "weather",
    "last_poll": 1708000000.0,
    "last_success": 1708000000.0,
    "last_error": null,
    "poll_count": 42,
    "error_count": 0
}
```

---

## Redis Config Keys

**Pattern:** `config:{section}`
**Type:** String (JSON)
**TTL:** None (persists until overwritten)

Written by the web gateway on config changes. Seeded from `.env` on first boot
by the orchestrator (using `SET NX` to avoid overwriting existing values).

| Key               | Example Value                                                        |
|-------------------|----------------------------------------------------------------------|
| `config:global`   | `{"cache_ttl": 60}`                                                  |
| `config:display`  | `{"rotation": 0, "scroll_speed": 0.08, "icon_duration": 1.5}`       |
| `config:sleep`    | `{"start_hour": 23, "end_hour": 7, "disable_pi_leds": false}`       |
| `config:weather`  | `{"location": "London"}`                                             |
| `config:pihole`   | `{"host": "http://...", "password": "..."}`                          |
| `config:aranet4`  | `{"sensors": [{"label":"office","mac":"AA:BB:..."}], "timeout": 10}` |
| `config:camera`   | `{"cameras": [...]}`                                                 |
| `config:schedule` | `{"tailscale": 30, "pihole": 30, "system": 30, "aranet4": 60, "weather": 300}` |
| `config:auth`     | `{"enabled": true, "username": "admin", "password_hash": "..."}`    |

---

## Pub/Sub Channels

### Data Updates

| Field      | Value                                   |
|------------|-----------------------------------------|
| Channel    | `data:{source_id}`                      |
| Publisher  | Source services (after writing to Redis) |
| Subscriber | Web gateway (for WebSocket push)        |

Payload:

```json
{"source_id": "weather", "timestamp": 1708000000.0}
```

### Commands (to services)

| Field      | Value                                        |
|------------|----------------------------------------------|
| Channel    | `cmd:{source_id}`                            |
| Publisher  | Web gateway                                  |
| Subscriber | Persistent/demand-started services           |

Payload:

```json
{
    "action": "clear",
    "request_id": "uuid-here",
    "params": {},
    "timestamp": 1708000000.0
}
```

### Command Responses

| Field      | Value                                              |
|------------|----------------------------------------------------|
| Channel    | `cmd:{source_id}:response:{request_id}`           |
| Publisher  | Service that handled the command                    |
| Subscriber | Web gateway (waiting for response)                 |

Payload:

```json
{
    "request_id": "uuid-here",
    "status": "ok",
    "data": {},
    "error": null
}
```

### Orchestrator Commands

| Field      | Value                       |
|------------|-----------------------------|
| Channel    | `cmd:orchestrator`          |
| Publisher  | Web gateway                 |
| Subscriber | Orchestrator service        |

Actions:

- `{"action": "start_camera", "request_id": "..."}` -- start camera container
- `{"action": "stop_camera", "request_id": "..."}` -- publish stop to camera, it self-terminates
- `{"action": "trigger", "params": {"service": "source-aranet4"}, "request_id": "..."}` -- run ephemeral source immediately
- `{"action": "scan_aranet4", "request_id": "..."}` -- start aranet4 container in scan mode (MODE=scan), returns discovered BLE devices
- `{"action": "discover_cameras", "request_id": "..."}` -- start camera container in discover mode (MODE=discover), returns found RTSP cameras

Response data examples:

```json
// scan_aranet4
{"devices": [{"name": "Aranet4 12345", "mac": "AA:BB:CC:DD:EE:FF", "rssi": -60}, ...]}

// discover_cameras
{"cameras": [{"name": "Camera 1", "host": "192.168.1.100", "port": 554}, ...]}
```

### Config Change Notifications

| Field      | Value                                             |
|------------|---------------------------------------------------|
| Channel    | `config:changed`                                  |
| Publisher  | Web gateway (after writing config to Redis)       |
| Subscriber | Orchestrator, source-sensehat, persistent services|

Payload:

```json
{"section": "weather", "timestamp": 1708000000.0}
```

### Stream Lifecycle Events

| Field      | Value                                           |
|------------|-------------------------------------------------|
| Channel    | `stream:ended`                                  |
| Publisher  | source-camera (when FFmpeg stops / user stops)  |
| Subscriber | Orchestrator (to clean up container)            |

Payload:

```json
{"source_id": "network_camera", "reason": "user_stopped", "timestamp": 1708000000.0}
```

### LED Matrix State (for web preview)

| Field      | Value                                              |
|------------|----------------------------------------------------|
| Channel    | `matrix:state`                                     |
| Publisher  | source-sensehat (every 500ms when display active)  |
| Subscriber | Web gateway (for /ws/grid WebSocket)               |

Payload:

```json
{
    "pixels": [[255,0,0], [0,255,0]],
    "mode": "scrolling",
    "rotation": 0,
    "available": true
}
```

64 elements in the pixels array (8x8 grid, row-major).

---

## Service Environment Variables

### All services

| Variable    | Required | Default              | Description            |
|-------------|----------|----------------------|------------------------|
| `REDIS_URL` | Yes      | `redis://redis:6379` | Redis connection URL   |

### source-tailscale

No extra config. Uses host Tailscale socket mounted at `/var/run/tailscale/tailscaled.sock`.

### source-pihole

| Variable          | Required | Default | Description              |
|-------------------|----------|---------|--------------------------|
| `PIHOLE_HOST`     | Yes      | --      | Pi-hole URL              |
| `PIHOLE_PASSWORD` | No       | `""`    | Pi-hole app password     |

### source-system

No extra config. Reads from `/host/proc` and `/host/sys` mounts.

### source-sensehat

| Variable           | Required | Default | Description                        |
|--------------------|----------|---------|------------------------------------|
| `DISPLAY_ROTATION` | No       | `0`     | LED rotation: 0, 90, 180, 270     |
| `SCROLL_SPEED`     | No       | `0.08`  | Text scroll speed                  |
| `ICON_DURATION`    | No       | `1.5`   | Icon display duration (seconds)    |
| `SLEEP_START`      | No       | `23`    | Hour to blank display              |
| `SLEEP_END`        | No       | `7`     | Hour to resume display             |
| `DISABLE_PI_LEDS`  | No       | `false` | Disable Pi onboard LEDs in sleep   |

### source-aranet4

| Variable           | Required | Default  | Description                            |
|--------------------|----------|----------|----------------------------------------|
| `ARANET4_SENSORS`  | Yes      | `[]`     | JSON: `[{"label":"x","mac":"AA:BB:"}]` |
| `ARANET4_TIMEOUT`  | No       | `10`     | BLE scan timeout (seconds)             |
| `MODE`             | No       | `"poll"` | `"poll"` = read sensors, `"scan"` = discover nearby devices |

### source-weather

| Variable           | Required | Default | Description                  |
|--------------------|----------|---------|------------------------------|
| `WEATHER_LOCATION` | No       | `""`    | Location for wttr.in (empty=auto) |

### source-camera

| Variable         | Required | Default    | Description                                              |
|------------------|----------|------------|----------------------------------------------------------|
| `CAMERA_CONFIG`  | Yes      | `[]`       | JSON: camera config array                                |
| `HLS_OUTPUT_DIR` | No       | `/hls`     | HLS output directory                                     |
| `MODE`           | No       | `"stream"` | `"stream"` = run HLS stream, `"discover"` = scan network for RTSP cameras |

### web-gateway

| Variable             | Required | Default | Description                    |
|----------------------|----------|---------|--------------------------------|
| `AUTH_ENABLED`       | No       | `true`  | Enable HTTP Basic Auth         |
| `AUTH_USERNAME`      | No       | `""`    | Auth username                  |
| `AUTH_PASSWORD_HASH` | No       | `""`    | Bcrypt password hash           |
| `CORS_ORIGINS`       | No       | `""`    | Comma-separated allowed origins|

### orchestrator

| Variable                | Required | Default | Description               |
|-------------------------|----------|---------|---------------------------|
| `COMPOSE_PROJECT_NAME`  | Yes      | --      | Docker Compose project    |
| `SCHEDULE_TAILSCALE`    | No       | `30`    | Poll interval (seconds)   |
| `SCHEDULE_PIHOLE`       | No       | `30`    | Poll interval (seconds)   |
| `SCHEDULE_SYSTEM`       | No       | `30`    | Poll interval (seconds)   |
| `SCHEDULE_ARANET4`      | No       | `60`    | Poll interval (seconds)   |
| `SCHEDULE_WEATHER`      | No       | `300`   | Poll interval (seconds)   |

---

## Common Library Exports (sense-common)

Every service imports from `sense_common`:

```python
# Models
from sense_common.models import (
    SensorReading,
    SourceMetadata,
    SourceStatus,
    Command,
    CommandResponse,
)

# Redis client
from sense_common.redis_client import (
    create_redis,
    write_readings,
    read_source,
    read_all_sources,
    write_metadata,
    write_status,
    read_all_statuses,
    publish_data,
    publish_command,
    subscribe_commands,
    publish_response,
    wait_response,
    read_config,
    write_config,
    subscribe_config_changes,
    seed_config_from_env,
)

# Base classes
from sense_common.ephemeral import EphemeralSource
from sense_common.persistent import PersistentSource

# Config helpers
from sense_common.config import (
    get_env,
    get_env_int,
    get_env_float,
    get_env_bool,
    get_env_json,
    get_redis_url,
    get_config_value,
)
```

---

## Config Read Pattern

Every service follows this pattern for reading configuration:

```python
# 1. Try Redis config (latest, may have been changed via dashboard)
redis_config = await read_config(redis, "weather")

# 2. Fall back to environment variable
location = get_config_value(redis_config, "WEATHER_LOCATION", default="")
```

**Behavior:**

- **First boot** (no Redis config yet): orchestrator seeds `config:*` from `.env`, sources read from Redis
- **After a config change** via dashboard: gateway writes to `config:*`, sources read updated values
- **Ephemeral sources**: get fresh config every poll cycle (no restart needed)
- **Persistent sources**: subscribe to `config:changed` for hot-reload
- **Full restart** (`docker compose down/up`): orchestrator re-seeds with `SET NX` (won't overwrite dashboard changes)

---

## Gateway API Endpoints

5 REST patterns + 2 WebSocket endpoints.

| Method | Path                         | Auth | Description                              |
|--------|------------------------------|------|------------------------------------------|
| GET    | `/api/sources`               | Yes  | All sources: readings + status           |
| GET    | `/api/sources/{source_id}`   | Yes  | Single source: readings + status         |
| GET    | `/api/config`                | Yes  | All config sections                      |
| POST   | `/api/config`                | Yes  | Update config sections                   |
| POST   | `/api/command/{target}`      | Yes  | Dispatch command to a service            |
| GET    | `/api/stream/{path:path}`    | Yes  | Serve HLS playlist + segments            |
| GET    | `/health`                    | No   | Gateway + Redis alive (Docker/Traefik)   |
| WS     | `/ws/sources`                | No   | Real-time source data updates            |
| WS     | `/ws/grid`                   | No   | LED matrix state (500ms)                 |

### Response shapes

```json
// GET /api/sources — readings + status merged per source
{
    "tailscale": {
        "readings": {
            "connected": {"value": true, "unit": null, "timestamp": 1708000000.0},
            "device_count": {"value": 5, "unit": "devices", "timestamp": 1708000000.0}
        },
        "status": {"last_poll": 1708000000.0, "last_success": 1708000000.0, "last_error": null, "poll_count": 42, "error_count": 0}
    },
    "weather": {
        "readings": {"weather_temp": {"value": 18.0, "unit": "C", "timestamp": 1708000000.0}, "...": "..."},
        "status": {"last_poll": 1708000000.0, "last_success": 1708000000.0, "last_error": null, "poll_count": 3, "error_count": 0}
    }
}

// GET /api/sources/{source_id} — same inner shape
{"readings": {"...": "..."}, "status": {"...": "..."}}

// GET /api/config
{"display": {"rotation": 0}, "sleep": {"start_hour": 23}, "weather": {"location": "London"}, "...": "..."}

// POST /api/config — partial update
// request:  {"display": {"rotation": 180}, "weather": {"location": "Paris"}}
// response: {"status": "ok", "sections_updated": ["display", "weather"]}

// POST /api/command/{target}
// request:  {"action": "clear"}
// response: {"success": true, "message": "Display cleared"}

// GET /health
{"status": "healthy"}

// WS /ws/sources — pushes same shape as GET /api/sources
// WS /ws/grid — pushes: {"pixels": [[r,g,b],...], "mode": "scrolling", "rotation": 0, "available": true}
```

A source with `"status": null` means the status TTL expired (source unavailable).
A source with `"readings": {}` but valid status means the source is running but has no data yet.
