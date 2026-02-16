# Phase 2: Simple Source Services

> **Type:** PARALLEL -- can run after Phase 1 completes.
> **Owner:** `services/source-weather/`, `services/source-pihole/`, `services/source-tailscale/`, `services/source-system/`
> **Depends on:** Phase 1 (sense-common library, workspace structure).

## Goal

Implement 4 ephemeral poll-and-die source services. Each starts, reads config from
Redis, polls its data source once, writes readings to Redis, and exits.

## Reference Code

- `legacy/sense_pulse/devices/pihole.py`
- `legacy/sense_pulse/devices/tailscale.py`
- `legacy/sense_pulse/devices/system.py`
- `legacy/sense_pulse/datasources/pihole_source.py`
- `legacy/sense_pulse/datasources/tailscale_source.py`
- `legacy/sense_pulse/datasources/system_source.py`
- `legacy/sense_pulse/datasources/weather_source.py`

---

## Tasks

### 2.1 source-weather

**Files:**

```
services/source-weather/
+-- pyproject.toml
+-- Dockerfile
+-- weather/
|   +-- __init__.py
|   +-- main.py
|   +-- source.py
+-- tests/
    +-- __init__.py
    +-- test_source.py
```

- [ ] `source.py` -- `WeatherSource(EphemeralSource)`:
  - `source_id = "weather"`, refresh_interval = 300
  - `async poll(redis)`:
    1. Read config: `config = await read_config(redis, "weather")`
    2. Get location: `location = get_config_value(config, "WEATHER_LOCATION", "")`
    3. GET `https://wttr.in/{location}?format=j1` via `httpx.AsyncClient`
    4. Parse response into 26 scalar `SensorReading` objects (see CONTRACT.md):
       - 11 current condition readings (weather_temp, weather_feels_like, etc.)
       - 15 forecast readings: `forecast_d{0-2}_{date,max_temp,min_temp,avg_temp,description}`
    5. Handle: HTTP errors, timeout, invalid JSON -- return empty list on failure
- [ ] `main.py` -- entry point:
  ```python
  import asyncio
  from weather.source import WeatherSource
  from sense_common.config import get_redis_url
  source = WeatherSource()
  asyncio.run(source.run(get_redis_url()))
  ```
- [ ] Dockerfile (Alpine):
  - Base: `python:3.12-alpine`
  - Install: uv + workspace deps
  - Build context: project root
  - CMD: `uv run --package sense-source-weather python -m weather.main`
- [ ] `test_source.py`:
  - Mock httpx response with sample wttr.in JSON
  - Verify 26 SensorReading objects returned with correct sensor_ids (11 current + 15 forecast)
  - Verify error handling (HTTP 500, timeout, malformed JSON)
  - Verify Redis writes via fakeredis (integration test of full run())

### 2.2 source-pihole

**Files:**

```
services/source-pihole/
+-- pyproject.toml
+-- Dockerfile
+-- pihole/
|   +-- __init__.py
|   +-- main.py
|   +-- source.py
|   +-- client.py
+-- tests/
    +-- __init__.py
    +-- test_source.py
    +-- test_client.py
```

- [ ] `client.py` -- extract from `legacy/sense_pulse/devices/pihole.py`:
  - `PiHoleClient` class with async httpx client
  - `async authenticate(host, password) -> session_id`
  - `async fetch_stats(host, session_id) -> dict`
  - Tenacity retry on connection/timeout errors (3 attempts, exponential backoff)
  - Replace `sense_pulse.web.log_handler` imports with standard `logging`
- [ ] `source.py` -- `PiHoleSource(EphemeralSource)`:
  - `source_id = "pihole"`, refresh_interval = 30
  - `async poll(redis)`:
    1. Read config: `config = await read_config(redis, "pihole")`
    2. Get host/password from config, fallback to env
    3. Create `PiHoleClient`, authenticate, fetch stats
    4. Return 3 SensorReadings: `queries_today`, `ads_blocked_today`, `ads_percentage_today`
- [ ] `main.py` -- entry point
- [ ] Dockerfile (Alpine)
- [ ] `test_client.py` -- mock httpx, test auth flow + stats fetch + retry behavior
- [ ] `test_source.py` -- mock client, verify SensorReading output + Redis writes

### 2.3 source-tailscale

**Files:**

```
services/source-tailscale/
+-- pyproject.toml
+-- Dockerfile
+-- tailscale/
|   +-- __init__.py
|   +-- main.py
|   +-- source.py
+-- tests/
    +-- __init__.py
    +-- test_source.py
```

- [ ] `source.py` -- `TailscaleSource(EphemeralSource)`:
  - `source_id = "tailscale"`, refresh_interval = 30
  - `async poll(redis)`:
    1. Run `tailscale status --json` via `asyncio.create_subprocess_exec`
    2. Parse JSON: check `BackendState == "Running"` for connected status
    3. Count online peers from `Peer` dict
    4. Return 2 SensorReadings: `connected` (bool), `device_count` (int)
    5. Handle: `FileNotFoundError` (tailscale not installed), timeout (5s), JSON parse error
- [ ] `main.py` -- entry point
- [ ] Dockerfile (Alpine + tailscale):
  - `RUN apk add --no-cache tailscale`
  - Note: container mounts host Tailscale socket at `/var/run/tailscale/tailscaled.sock`
- [ ] `test_source.py`:
  - Mock `asyncio.create_subprocess_exec` with sample JSON output
  - Test connected + disconnected states
  - Test tailscale not installed (FileNotFoundError)
  - Test timeout handling

### 2.4 source-system

**Files:**

```
services/source-system/
+-- pyproject.toml
+-- Dockerfile
+-- system/
|   +-- __init__.py
|   +-- main.py
|   +-- source.py
+-- tests/
    +-- __init__.py
    +-- test_source.py
```

- [ ] `source.py` -- `SystemSource(EphemeralSource)`:
  - `source_id = "system"`, refresh_interval = 30
  - `async poll(redis)`:
    1. If `/host/proc` exists, set `os.environ["HOST_PROC"] = "/host/proc"` (containerized psutil)
    2. Use `psutil.cpu_percent(interval=1)` (blocking, run in `asyncio.to_thread`)
    3. Use `psutil.virtual_memory().percent`
    4. Use `os.getloadavg()[0]`
    5. Use `psutil.sensors_temperatures()` for CPU temp (try `cpu_thermal`, then `coretemp`)
    6. Return 4 SensorReadings: `cpu_percent`, `memory_percent`, `load_1min`, `cpu_temp`
- [ ] `main.py` -- entry point
- [ ] Dockerfile (Alpine + psutil build deps):
  - `RUN apk add --no-cache gcc musl-dev linux-headers`
  - Volume mounts (in compose): `/proc:/host/proc:ro`, `/sys:/host/sys:ro`
- [ ] `test_source.py`:
  - Mock `psutil.cpu_percent`, `virtual_memory`, `sensors_temperatures`
  - Verify 4 SensorReadings with correct units
  - Test missing temperature sensors (returns 0.0)

---

## Validation (per service)

- [ ] `uv run --package <name> pytest` passes
- [ ] `docker build -f services/source-<name>/Dockerfile .` succeeds
- [ ] Container runs against local Redis and writes expected keys (manual integration test)

## Dockerfile Template

All 4 services use the same pattern:

```dockerfile
FROM python:3.12-alpine AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# Dependency layer (cached unless pyproject.toml or uv.lock changes)
COPY pyproject.toml uv.lock ./
COPY services/common/pyproject.toml services/common/pyproject.toml
COPY services/source-weather/pyproject.toml services/source-weather/pyproject.toml
RUN uv sync --package sense-source-weather --frozen --no-dev --no-install-workspace

# Source layer (changes frequently)
COPY services/common/sense_common/ services/common/sense_common/
COPY services/source-weather/ services/source-weather/
RUN uv sync --package sense-source-weather --frozen --no-dev

CMD ["uv", "run", "--package", "sense-source-weather", "python", "-m", "weather.main"]
```

Build context is always the project root (`.`). Dockerfile path is per-service.
