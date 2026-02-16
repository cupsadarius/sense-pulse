# Phase 5: Orchestrator Service

> **Type:** PARALLEL -- can run after Phase 1 completes.
> **Owner:** `services/orchestrator/`
> **Depends on:** Phase 1 (sense-common library).

## Goal

Build a lightweight always-running service that:

1. Triggers ephemeral source containers on configurable intervals
2. Handles demand-start requests (camera)
3. Seeds Redis config from `.env` on first boot
4. Monitors service health
5. Responds to config changes

## Reference Code

No direct legacy equivalent -- this is a new service replacing the monolith's
`DataCache` polling loop and `AppContext` lifecycle management.

---

## Tasks

### 5.1 Project structure

```
services/orchestrator/
+-- pyproject.toml
+-- Dockerfile
+-- orchestrator/
|   +-- __init__.py
|   +-- main.py              # Entry point
|   +-- runner.py             # Docker Compose container runner
|   +-- schedule.py           # Scheduling logic
|   +-- commands.py           # Redis command listener
|   +-- config_seeder.py      # Seed Redis config from .env on boot
|   +-- lifecycle.py          # Camera lifecycle management
|   +-- health.py             # Health monitoring
+-- tests/
    +-- __init__.py
    +-- test_runner.py
    +-- test_schedule.py
    +-- test_commands.py
    +-- test_config_seeder.py
    +-- test_lifecycle.py
```

### 5.2 Config seeder (`config_seeder.py`)

- [ ] `async seed_all_config(redis)`:
  - Read environment variables and seed Redis config keys using `SET NX` (don't overwrite)
  - `PIHOLE_HOST`, `PIHOLE_PASSWORD` -> `config:pihole`
  - `WEATHER_LOCATION` -> `config:weather`
  - `ARANET4_SENSORS`, `ARANET4_TIMEOUT` -> `config:aranet4`
  - `CAMERA_CONFIG` -> `config:camera`
  - `DISPLAY_ROTATION`, `SCROLL_SPEED`, `ICON_DURATION` -> `config:display`
  - `SLEEP_START`, `SLEEP_END`, `DISABLE_PI_LEDS` -> `config:sleep`
  - `SCHEDULE_*` -> `config:schedule`
  - `AUTH_ENABLED`, `AUTH_USERNAME`, `AUTH_PASSWORD_HASH` -> `config:auth`
- [ ] Use `seed_config_from_env()` from sense-common (which uses `SET NX` internally)
- [ ] Run once at startup before starting the schedule loop

### 5.3 Container runner (`runner.py`)

- [ ] `DockerRunner` class:
  - `async run_ephemeral(service: str, env: dict | None = None) -> bool`:
    - Execute: `docker compose --profile poll run --rm {-e KEY=VAL for env} {service}`
    - Via `asyncio.create_subprocess_exec`
    - Optional `env` dict passed as `-e KEY=VAL` flags to `docker compose run`
    - Timeout: 60s (BLE scans can take ~15s), configurable per service
    - Return True on exit code 0, False otherwise
    - Log stdout/stderr on failure
  - `async start_service(service: str) -> bool`:
    - Execute: `docker compose --profile camera up -d {service}`
    - Return True on success
  - `async stop_service(service: str) -> bool`:
    - Execute: `docker compose --profile camera stop {service}`
    - Return True on success
  - Track currently running containers in a `set[str]` to prevent double-spawning
  - On completion: remove from running set
  - `COMPOSE_PROJECT_NAME` from env for correct compose context

### 5.4 Schedule loop (`schedule.py`)

- [ ] `Scheduler` class:
  - Load schedule from Redis `config:schedule` (fallback to env vars):
    ```python
    schedules = {
        "source-tailscale": 30,
        "source-pihole": 30,
        "source-system": 30,
        "source-aranet4": 60,
        "source-weather": 300,
    }
    ```
  - Track `last_run: dict[str, float]` per service (initialized to 0)
  - Main loop (tick every 5s):
    1. For each service: check if `now - last_run[service] >= interval`
    2. If due AND not already running: spawn `runner.run_ephemeral(service)` as asyncio task
    3. Update `last_run[service]` when task starts
  - On startup: trigger ALL services immediately (initial data load)
  - Multiple ephemeral containers can run concurrently
  - `update_schedule(new_schedules: dict)` method for hot-reload

### 5.5 Command listener (`commands.py`)

- [ ] Subscribe to `cmd:orchestrator` Redis channel
- [ ] Handle commands:
  - `start_camera`:
    1. Start camera container via `runner.start_service("source-camera")`
    2. Respond `{status: "ok"}` or `{status: "error", error: "..."}`
  - `stop_camera`:
    1. Publish `cmd:network_camera {action: "stop"}` (camera self-terminates)
    2. Respond `{status: "ok"}`
    3. Camera cleanup handled by lifecycle listener
  - `trigger`:
    1. `params.service` -- name of ephemeral service to trigger immediately
    2. `runner.run_ephemeral(params.service)`
    3. Respond with success/failure
  - `scan_aranet4`:
    1. Start source-aranet4 container with `MODE=scan` env override
    2. `runner.run_ephemeral("source-aranet4", env={"MODE": "scan"})`
    3. Container scans BLE for nearby Aranet4 devices, writes results to `scan:co2` Redis key, exits
    4. Read `scan:co2` from Redis, return found devices in command response
    5. Respond `{status: "ok", data: {devices: [{name: "...", mac: "AA:BB:...", rssi: -60}, ...]}}`
  - `discover_cameras`:
    1. Start source-camera container with `MODE=discover` env override
    2. `runner.run_ephemeral("source-camera", env={"MODE": "discover"})`
    3. Container scans local network for RTSP cameras, writes results to `scan:network_camera` Redis key, exits
    4. Read `scan:network_camera` from Redis, return found cameras in command response
    5. Respond `{status: "ok", data: {cameras: [{name: "...", host: "...", port: 554}, ...]}}`
  - `restart_service`:
    1. `runner.stop_service(params.service)` then `runner.start_service(params.service)`
    2. Respond with success/failure
- [ ] Publish responses to `cmd:orchestrator:response:{request_id}`

### 5.6 Camera lifecycle (`lifecycle.py`)

- [ ] Subscribe to `stream:ended` Redis channel
- [ ] On `stream:ended` event:
  1. Log event with reason
  2. Wait 2 seconds (let container finish cleanup)
  3. Run `runner.stop_service("source-camera")` to ensure container is cleaned up
  4. Update `status:network_camera` in Redis to reflect stopped state

### 5.7 Config change listener

- [ ] Subscribe to `config:changed` Redis channel
- [ ] On `{section: "schedule"}`:
  - Read `config:schedule` from Redis
  - Call `scheduler.update_schedule(new_values)` to update intervals immediately
- [ ] On `{section: "auth"}`:
  - Log warning: "Auth config changed, web-gateway restart required"
  - Optionally: `runner.stop_service("web-gateway")` + `runner.start_service("web-gateway")`
- [ ] On `{section: "camera"}`:
  - If camera is currently running: log warning "Camera config changed, restart stream to apply"
  - (Camera reads config from Redis on next start, no action needed)
- [ ] Other sections: no action (ephemeral sources pick up changes automatically)

### 5.8 Health monitoring (`health.py`)

- [ ] `HealthMonitor` class:
  - Runs every 60 seconds
  - Read all `status:*` keys from Redis
  - For each source: check if `last_success` is within `3 * refresh_interval`
  - Log warning if a source is overdue
  - Write own status to `status:orchestrator`

### 5.9 Main entry point (`main.py`)

- [ ] Connect to Redis
- [ ] Run config seeder (once)
- [ ] Create all components: runner, scheduler, command listener, lifecycle, health monitor
- [ ] Run all concurrently:
  ```python
  await asyncio.gather(
      scheduler.run(),
      command_listener.run(),
      lifecycle_listener.run(),
      config_change_listener.run(),
      health_monitor.run(),
  )
  ```
- [ ] Signal handling (SIGTERM/SIGINT):
  - Set shutdown flag
  - Wait for any running ephemeral containers to finish (up to 30s)
  - Clean exit

### 5.10 Dockerfile

```dockerfile
FROM python:3.12-alpine
RUN apk add --no-cache docker-cli docker-cli-compose
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
# Standard uv install pattern...
CMD ["uv", "run", "--package", "sense-orchestrator", "python", "-m", "orchestrator.main"]
```

Mounts:
- `/var/run/docker.sock:/var/run/docker.sock` -- Docker socket for container management
- Project root or compose file for `docker compose` context

### 5.11 Tests

- [ ] `test_runner.py`:
  - Mock subprocess for `docker compose run/up/stop`
  - Verify correct commands constructed
  - Test double-spawn prevention
  - Test timeout handling
- [ ] `test_schedule.py`:
  - Verify services triggered at correct intervals
  - Verify immediate trigger on startup
  - Verify concurrent execution
  - Test `update_schedule()` hot-reload
- [ ] `test_commands.py`:
  - Fakeredis pub/sub
  - Verify start_camera, stop_camera, trigger, scan_aranet4, discover_cameras commands
  - Verify response publishing
- [ ] `test_config_seeder.py`:
  - Fakeredis
  - Verify NX behavior (doesn't overwrite existing keys)
  - Verify all env vars mapped correctly
- [ ] `test_lifecycle.py`:
  - Fakeredis pub/sub for stream:ended
  - Verify cleanup triggered

---

## Validation

- [ ] `uv run --package sense-orchestrator pytest` passes
- [ ] Orchestrator starts and triggers all ephemeral services on first boot
- [ ] Services are re-triggered at configured intervals
- [ ] `cmd:orchestrator` commands work (start_camera, stop_camera, trigger, scan_aranet4, discover_cameras)
- [ ] No double-spawning of same service
- [ ] Config seeding works (keys appear in Redis with NX behavior)
- [ ] Schedule hot-reload works via config:changed
- [ ] Camera lifecycle: start -> stream:ended -> cleanup
