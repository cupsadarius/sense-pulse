# Phase 6: Web Gateway (FastAPI)

> **Type:** PARALLEL -- can run after Phase 1 completes.
> **Owner:** `services/web-gateway/`
> **Depends on:** Phase 1 (sense-common library).

## Goal

Build a minimal JSON API gateway. No HTML templates. Reads all data from Redis,
dispatches commands via Redis pub/sub, serves HLS files from a shared volume.
The SvelteKit frontend (Phase 7) consumes this API.

## Reference Code

- `legacy/sense_pulse/web/routes.py` -- API endpoints
- `legacy/sense_pulse/web/app.py` -- FastAPI app factory
- `legacy/sense_pulse/web/auth.py` -- authentication

---

## API Design

5 REST patterns + 2 WebSocket endpoints. That's the whole gateway.

### Endpoints

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

---

## Tasks

### 6.1 Project structure

```
services/web-gateway/
+-- pyproject.toml
+-- Dockerfile
+-- gateway/
|   +-- __init__.py
|   +-- main.py                # uvicorn entry point
|   +-- app.py                 # FastAPI app factory
|   +-- deps.py                # FastAPI dependencies (Redis, auth)
|   +-- auth.py                # HTTP Basic Auth
|   +-- routes/
|   |   +-- __init__.py
|   |   +-- sources.py         # GET /api/sources, GET /api/sources/{source_id}
|   |   +-- config.py          # GET/POST /api/config
|   |   +-- command.py         # POST /api/command/{target}
|   |   +-- stream.py          # GET /api/stream/{path}
|   |   +-- health.py          # GET /health
|   +-- websocket/
|       +-- __init__.py
|       +-- sources.py         # WS /ws/sources
|       +-- grid.py            # WS /ws/grid
+-- tests/
    +-- __init__.py
    +-- test_sources.py
    +-- test_config.py
    +-- test_command.py
    +-- test_stream.py
    +-- test_health.py
    +-- test_auth.py
    +-- test_websocket.py
```

### 6.2 App factory and dependencies (`app.py`, `deps.py`)

- [ ] `app.py` -- `create_app() -> FastAPI`:
  - Create FastAPI instance with lifespan handler
  - On startup: connect to Redis, store on `app.state.redis`
  - On shutdown: close Redis connection
  - Add CORS middleware (origins from `CORS_ORIGINS` env)
  - Include all route modules
- [ ] `deps.py`:
  - `get_redis(request) -> Redis` -- FastAPI dependency, gets Redis from `app.state`
  - `require_auth(credentials) -> str` -- FastAPI dependency for auth (see 6.3)

### 6.3 Authentication (`auth.py`)

- [ ] Port from `legacy/sense_pulse/web/auth.py`
- [ ] HTTP Basic Auth using `passlib` + `bcrypt`
- [ ] On startup: read auth config from Redis `config:auth` (fallback to env vars)
- [ ] `require_auth` dependency: verify credentials, return username
- [ ] If auth disabled: allow all requests
- [ ] Constant-time username comparison to prevent timing attacks

### 6.4 Sources route (`routes/sources.py`)

- [ ] `GET /api/sources` (auth required):
  - Read all source readings from Redis via `read_all_sources(redis)`
  - Read all source statuses from Redis via `read_all_statuses(redis)`
  - Merge into unified response: `{source_id: {readings: {...}, status: {...}}, ...}`
  - Sources with expired status key (TTL lapsed) get `status: null`
  - Sources with status but no readings get `readings: {}`
- [ ] `GET /api/sources/{source_id}` (auth required):
  - Read single source readings via `read_source(redis, source_id)`
  - Read single source status from Redis `status:{source_id}`
  - Return `{readings: {...}, status: {...}}`
  - Return 404 if source_id has no readings AND no status

### 6.5 Config route (`routes/config.py`)

- [ ] `GET /api/config` (auth required):
  - Read all `config:*` keys from Redis
  - Return merged config object: `{display: {...}, sleep: {...}, schedule: {...}, weather: {...}, pihole: {...}, aranet4: {...}, camera: {...}, auth: {...}}`
- [ ] `POST /api/config` (auth required):
  - Body: `{display?: {...}, sleep?: {...}, weather?: {...}, schedule?: {...}, aranet4?: {...}, camera?: {...}, auth?: {...}}`
  - All config sections in one endpoint -- no separate aranet4/camera config routes
  - Validate each section (e.g., rotation must be 0/90/180/270)
  - For each changed section:
    1. Write to Redis: `write_config(redis, section, data)`
    2. Publish: `config:changed {section}`
  - Return: `{status: "ok", sections_updated: ["display", "sleep"]}`

### 6.6 Command route (`routes/command.py`)

- [ ] `POST /api/command/{target}` (auth required):
  - `target` is the service to command: `"sensors"`, `"network_camera"`, `"orchestrator"`
  - Validate `target` against known service list
  - Body: `{action: str, params?: dict}`
  - Publish command to `cmd:{target}` via `publish_command()`
  - Wait for response via `wait_response()` with configurable timeout:
    - Default: 5s
    - `start_camera`: 10s (container startup)
    - `scan_aranet4`: 30s (BLE scan)
    - `discover_cameras`: 30s (port scan)
  - Return: `{success: bool, message: str, data?: dict}`

Example commands:

```
POST /api/command/sensors        {action: "clear"}
POST /api/command/sensors        {action: "set_rotation", params: {rotation: 180}}
POST /api/command/orchestrator   {action: "start_camera"}
POST /api/command/orchestrator   {action: "stop_camera"}
POST /api/command/orchestrator   {action: "trigger", params: {service: "source-aranet4"}}
POST /api/command/network_camera {action: "ptz_move", params: {direction: "up", step: 0.1}}
POST /api/command/orchestrator   {action: "scan_aranet4"}
POST /api/command/orchestrator   {action: "discover_cameras"}
```

### 6.7 Stream route (`routes/stream.py`)

- [ ] `GET /api/stream/{path:path}`:
  - Serve HLS files from `/hls` shared volume (read-only)
  - `stream.m3u8` -- playlist, `Cache-Control: no-cache`
  - `*.ts` -- video segments
  - Sanitize path: `Path(path).name` to prevent directory traversal
  - Return 503 if playlist doesn't exist (stream not running)
  - Return 404 if segment not found

### 6.8 Health route (`routes/health.py`)

- [ ] `GET /health` (no auth):
  - Ping Redis
  - Return `{status: "healthy"}` on success
  - Return 503 `{status: "unhealthy"}` if Redis unreachable
  - Used by Docker HEALTHCHECK and Traefik

### 6.9 WebSocket endpoints

#### `/ws/sources` (`websocket/sources.py`)

- [ ] Accept WebSocket connection
- [ ] Subscribe to all `data:*` Redis channels
- [ ] On data notification:
  - Read the updated source readings + status from Redis
  - Batch updates: aggregate for up to 5 seconds
  - Push full snapshot in same shape as `GET /api/sources`
- [ ] Fallback: if no pub/sub messages after 30s, poll Redis and push
- [ ] Send heartbeat every 30s to keep connection alive
- [ ] Handle WebSocket disconnect gracefully (unsubscribe, cleanup)

#### `/ws/grid` (`websocket/grid.py`)

- [ ] Accept WebSocket connection
- [ ] Subscribe to `matrix:state` Redis channel
- [ ] Forward each matrix state message to client
- [ ] Fallback: if no messages after 1s, send empty state
- [ ] Handle disconnect gracefully

### 6.10 Dockerfile

```dockerfile
FROM python:3.12-alpine
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
# Standard uv install pattern (dependency layer + source layer)
EXPOSE 8080
HEALTHCHECK CMD wget -q --spider http://localhost:8080/health || exit 1
CMD ["uv", "run", "--package", "sense-gateway", "uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

Mounts: `hls-data` volume at `/hls` (read-only).

### 6.11 Tests

- [ ] `test_sources.py`: fakeredis with pre-seeded data, verify merged readings+status shape for both all and single source
- [ ] `test_config.py`: verify GET reads from Redis, POST writes + publishes config:changed for multiple sections
- [ ] `test_command.py`: verify command published to correct channel, response waited, timeout handling
- [ ] `test_stream.py`: mock filesystem, verify HLS file serving, path sanitization, 503/404 responses
- [ ] `test_health.py`: verify Redis ping, test 503 on failure
- [ ] `test_auth.py`: test enabled/disabled, valid/invalid credentials, timing-safe comparison
- [ ] `test_websocket.py`: mock Redis pub/sub, verify data push matches GET /api/sources shape, heartbeat, disconnect

---

## API Response Shapes (for Frontend Agent)

```typescript
// GET /api/sources
{
  tailscale: {
    readings: {
      connected: {value: true, unit: null, timestamp: 170800},
      device_count: {value: 5, unit: "devices", timestamp: 170800}
    },
    status: {last_poll: 170800, last_success: 170800, last_error: null, poll_count: 42, error_count: 0}
  },
  pihole: {
    readings: {
      queries_today: {value: 12345, unit: "queries", timestamp: 170800},
      ads_blocked_today: {value: 1234, unit: "ads", timestamp: 170800},
      ads_percentage_today: {value: 10.0, unit: "%", timestamp: 170800}
    },
    status: {last_poll: 170800, last_success: 170800, last_error: null, poll_count: 10, error_count: 0}
  },
  system: {
    readings: {
      cpu_percent: {value: 23.5, unit: "%", timestamp: 170800},
      memory_percent: {value: 61.2, unit: "%", timestamp: 170800},
      load_1min: {value: 1.23, unit: "load", timestamp: 170800},
      cpu_temp: {value: 52.3, unit: "C", timestamp: 170800}
    },
    status: {last_poll: 170800, last_success: 170800, last_error: null, poll_count: 100, error_count: 0}
  },
  sensors: {
    readings: {
      temperature: {value: 24.3, unit: "C", timestamp: 170800},
      humidity: {value: 45.2, unit: "%", timestamp: 170800},
      pressure: {value: 1013.2, unit: "mbar", timestamp: 170800}
    },
    status: {last_poll: 170800, last_success: 170800, last_error: null, poll_count: 100, error_count: 0}
  },
  co2: {
    readings: {
      "office:co2": {value: 450, unit: "ppm", timestamp: 170800},
      "office:temperature": {value: 22.1, unit: "C", timestamp: 170800},
      "office:humidity": {value: 45, unit: "%", timestamp: 170800},
      "office:pressure": {value: 1013.2, unit: "mbar", timestamp: 170800},
      "office:battery": {value: 85, unit: "%", timestamp: 170800}
    },
    status: {last_poll: 170800, last_success: 170800, last_error: null, poll_count: 5, error_count: 1}
  },
  weather: {
    readings: {
      weather_temp: {value: 18.0, unit: "C", timestamp: 170800},
      weather_conditions: {value: "Partly cloudy", unit: null, timestamp: 170800},
      forecast_d0_date: {value: "2026-02-16", unit: null, timestamp: 170800},
      forecast_d0_max_temp: {value: 12.0, unit: "C", timestamp: 170800},
      // ... 26 readings total: 11 current + 15 forecast
    },
    status: {last_poll: 170800, last_success: 170800, last_error: null, poll_count: 3, error_count: 0}
  },
  network_camera: {
    readings: {
      stream_status: {value: "streaming", unit: null, timestamp: 170800},
      stream_connected: {value: true, unit: null, timestamp: 170800},
      stream_uptime: {value: 3600.0, unit: "seconds", timestamp: 170800}
    },
    status: null  // null = status TTL expired, source considered unavailable
  }
}

// GET /api/sources/weather (same inner shape)
{
  readings: {weather_temp: {value: 18.0, unit: "C", timestamp: 170800}, ...},
  status: {last_poll: 170800, last_success: 170800, last_error: null, poll_count: 3, error_count: 0}
}

// GET /api/config
{
  display: {rotation: 0, scroll_speed: 0.08, icon_duration: 1.5},
  sleep: {start_hour: 23, end_hour: 7, disable_pi_leds: false},
  schedule: {tailscale: 30, pihole: 30, system: 30, aranet4: 60, weather: 300},
  weather: {location: "London"},
  pihole: {host: "http://...", password: "..."},
  aranet4: {sensors: [{label: "office", mac: "AA:BB:..."}], timeout: 10},
  camera: {cameras: [...]},
  auth: {enabled: true, username: "admin"}
}

// POST /api/config (partial update)
// request:  {display: {rotation: 180}, weather: {location: "Paris"}}
// response: {status: "ok", sections_updated: ["display", "weather"]}

// POST /api/command/sensors
// request:  {action: "clear"}
// response: {success: true, message: "Display cleared"}

// GET /health
{status: "healthy"}

// WS /ws/sources pushes same shape as GET /api/sources
// WS /ws/grid pushes: {pixels: [[r,g,b],...], mode: "scrolling", rotation: 0, available: true}
```

The gateway returns flat readings directly from Redis. The frontend reconstructs
grouped views (aranet4 per-sensor, weather forecast array) from sensor_id naming
conventions client-side.

---

## Validation

- [ ] `uv run --package sense-gateway pytest` passes
- [ ] `GET /api/sources` returns merged readings+status for all sources
- [ ] `GET /api/sources/{id}` returns single source, 404 for unknown
- [ ] `POST /api/command/{target}` dispatches and waits correctly
- [ ] `POST /api/config` writes to Redis and publishes config:changed
- [ ] WebSocket sends data in same shape as GET /api/sources
- [ ] HLS files served from shared volume
- [ ] Auth blocks unauthorized requests when enabled
- [ ] CORS headers present for configured origins
