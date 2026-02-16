# Phase 1: Foundation

> **Type:** SEQUENTIAL -- must complete before all parallel phases.
> **Owner:** `pyproject.toml` (root), `uv.lock`, `services/common/`, `legacy/`, `redis/`
> **Depends on:** Nothing.

## Goal

Set up the UV workspace, build the shared `sense-common` library, configure Redis,
and move the old monolith to `legacy/`. After this phase, all other phases can
run in parallel.

## Deliverables

After this phase, the following MUST be true:

1. `uv lock` succeeds at the workspace root
2. `uv sync --package sense-common` installs cleanly
3. `uv run --package sense-common pytest` passes
4. Every service can `from sense_common import ...` without errors
5. `plans/CONTRACT.md` is committed and finalized

---

## Tasks

### 1.1 Move monolith to legacy

- [ ] Create `legacy/` directory
- [ ] Move `src/sense_pulse/` to `legacy/sense_pulse/`
- [ ] Move `tests/` to `legacy/tests/`
- [ ] Move `config.example.yaml` to `legacy/config.example.yaml`
- [ ] Move `setup.sh` to `legacy/setup.sh`
- [ ] Move `sense-pulse.service` to `legacy/sense-pulse.service`
- [ ] Move `99-pi-leds.rules` to `legacy/99-pi-leds.rules`
- [ ] Keep at root: `CLAUDE.md`, `README.md`, `CHANGELOG.md`, `.github/`, `.pre-commit-config.yaml`

### 1.2 Create workspace root pyproject.toml

- [ ] Replace root `pyproject.toml` with UV workspace definition
- [ ] List all 10 workspace members under `[tool.uv.workspace]`
- [ ] Keep shared dev dependencies at root (ruff, black, mypy, pytest, fakeredis)
- [ ] Keep tool configs (ruff, black, mypy, pytest) at root
- [ ] Bump version to `0.12.0`, require Python `>=3.12`

Members list:

```
services/common
services/web-gateway
services/orchestrator
services/source-tailscale
services/source-pihole
services/source-system
services/source-sensehat
services/source-aranet4
services/source-weather
services/source-camera
```

### 1.3 Create stub pyproject.toml for every service

For each of the 10 workspace members:

- [ ] Create the directory structure: `services/<name>/pyproject.toml`
- [ ] Set `name`, `version = "0.12.0"`, `requires-python = ">=3.12"`
- [ ] Add `sense-common` as a workspace dependency (except for common itself)
- [ ] Add service-specific dependencies (see table below)
- [ ] Add `[build-system]` with hatchling
- [ ] Create placeholder `__init__.py` so the workspace resolves

**Dependency table:**

| Service            | Package Name            | Extra Dependencies                                                        |
|--------------------|-------------------------|---------------------------------------------------------------------------|
| common             | `sense-common`          | `redis[hiredis]>=5.2`, `pydantic>=2.10`                                  |
| web-gateway        | `sense-gateway`         | `fastapi>=0.115`, `uvicorn[standard]>=0.32`, `passlib>=1.7`, `bcrypt>=4.2` |
| orchestrator       | `sense-orchestrator`    | (none -- uses subprocess for docker CLI)                                  |
| source-tailscale   | `sense-source-ts`       | (none -- uses subprocess for tailscale CLI)                               |
| source-pihole      | `sense-source-pihole`   | `httpx>=0.28`, `tenacity>=9.0`                                            |
| source-system      | `sense-source-system`   | `psutil>=6.1`                                                             |
| source-sensehat    | `sense-source-sensehat` | `pyyaml>=6.0` (sense-hat via apt)                                         |
| source-aranet4     | `sense-source-aranet4`  | `aranet4>=2.3`                                                            |
| source-weather     | `sense-source-weather`  | `httpx>=0.28`                                                             |
| source-camera      | `sense-source-camera`   | `onvif-zeep>=0.2.12`                                                      |

### 1.4 Build sense-common library

This is the critical deliverable. Directory structure:

```
services/common/
+-- pyproject.toml
+-- sense_common/
|   +-- __init__.py
|   +-- models.py
|   +-- redis_client.py
|   +-- ephemeral.py
|   +-- persistent.py
|   +-- config.py
+-- tests/
    +-- __init__.py
    +-- test_models.py
    +-- test_redis_client.py
    +-- test_ephemeral.py
    +-- test_persistent.py
```

#### 1.4.1 Models (`sense_common/models.py`)

- [ ] `SensorReading(BaseModel)`:
  - `sensor_id: str`
  - `value: int | float | str | bool` (scalar only -- no dicts, no lists)
  - `unit: str | None = None`
  - `timestamp: float` (Unix epoch)
- [ ] `SourceMetadata(BaseModel)`:
  - `source_id: str`
  - `name: str`
  - `description: str`
  - `refresh_interval: int` (seconds)
  - `enabled: bool = True`
- [ ] `SourceStatus(BaseModel)`:
  - `source_id: str`
  - `last_poll: float | None = None`
  - `last_success: float | None = None`
  - `last_error: str | None = None`
  - `poll_count: int = 0`
  - `error_count: int = 0`
- [ ] `Command(BaseModel)`:
  - `action: str`
  - `request_id: str = Field(default_factory=lambda: str(uuid4()))`
  - `params: dict[str, Any] = {}`
  - `timestamp: float = Field(default_factory=time.time)`
- [ ] `CommandResponse(BaseModel)`:
  - `request_id: str`
  - `status: Literal["ok", "error"]`
  - `data: dict[str, Any] = {}`
  - `error: str | None = None`

#### 1.4.2 Redis client (`sense_common/redis_client.py`)

- [ ] `async create_redis(url: str) -> redis.asyncio.Redis` -- connection with retry (3 attempts, 1s backoff)
- [ ] `async write_readings(redis, source_id: str, readings: list[SensorReading], ttl: int = 60)` -- sets `source:{source_id}:{r.sensor_id}` = JSON `{"value": r.value, "unit": r.unit, "timestamp": r.timestamp}` with TTL
- [ ] `async read_source(redis, source_id: str) -> dict[str, Any]` -- SCAN for `source:{source_id}:*`, returns `{sensor_id: {"value": ..., "unit": ..., "timestamp": ...}}`
- [ ] `async read_all_sources(redis) -> dict[str, dict]` -- SCAN `source:*`, group by source_id
- [ ] `async write_metadata(redis, source_id: str, metadata: SourceMetadata)` -- sets `meta:{source_id}`, no TTL
- [ ] `async write_status(redis, source_id: str, status: SourceStatus)` -- sets `status:{source_id}` with 120s TTL
- [ ] `async read_all_statuses(redis) -> list[SourceStatus]` -- SCAN `status:*`, parse each
- [ ] `async publish_data(redis, source_id: str)` -- publish `{"source_id": ..., "timestamp": ...}` to `data:{source_id}`
- [ ] `async publish_command(redis, source_id: str, command: Command)` -- publish command JSON to `cmd:{source_id}`
- [ ] `async subscribe_commands(redis, source_id: str) -> AsyncIterator[Command]` -- subscribe to `cmd:{source_id}`, yield parsed Commands
- [ ] `async publish_response(redis, source_id: str, response: CommandResponse)` -- publish to `cmd:{source_id}:response:{response.request_id}`
- [ ] `async wait_response(redis, source_id: str, request_id: str, timeout: float = 5.0) -> CommandResponse | None` -- subscribe to response channel, wait with timeout
- [ ] `async read_config(redis, section: str) -> dict | None` -- GET `config:{section}`, parse JSON, return None if missing
- [ ] `async write_config(redis, section: str, data: dict)` -- SET `config:{section}` (no TTL)
- [ ] `async seed_config_from_env(redis, section: str, data: dict)` -- SET NX `config:{section}` (only writes if key doesn't exist)
- [ ] `async subscribe_config_changes(redis) -> AsyncIterator[str]` -- subscribe to `config:changed`, yield section names

#### 1.4.3 Ephemeral service base (`sense_common/ephemeral.py`)

- [ ] `EphemeralSource` (abstract base class):
  - `source_id: str` (abstract property)
  - `metadata: SourceMetadata` (abstract property)
  - `async poll(self, redis) -> list[SensorReading]` (abstract -- receives redis so it can read config)
  - `async run(self, redis_url: str) -> None`:
    1. Connect to Redis via `create_redis()`
    2. Call `self.poll(redis)` to get readings
    3. Call `write_readings()` with the results
    4. Call `write_status()` with success info
    5. Call `write_metadata()` with source metadata
    6. Call `publish_data()` to notify subscribers
    7. On exception: call `write_status()` with error info
    8. Finally: close Redis connection
    9. Exit (container dies)

#### 1.4.4 Persistent service base (`sense_common/persistent.py`)

- [ ] `PersistentSource` (abstract base class):
  - `source_id: str` (abstract property)
  - `metadata: SourceMetadata` (abstract property)
  - `async poll(self, redis) -> list[SensorReading]` (abstract)
  - `async handle_command(self, command: Command) -> CommandResponse` (abstract)
  - `async on_config_changed(self, redis, section: str) -> None` (virtual -- override for hot-reload)
  - `async run(self, redis_url: str, poll_interval: int) -> None`:
    1. Connect to Redis
    2. Write initial metadata
    3. Run three tasks concurrently via `asyncio.gather()`:
       - `_poll_loop(redis, poll_interval)` -- poll + write + publish on interval
       - `_command_listener(redis)` -- subscribe to `cmd:{source_id}`, dispatch to `handle_command()`
       - `_config_listener(redis)` -- subscribe to `config:changed`, dispatch to `on_config_changed()`
    4. Handle SIGTERM/SIGINT for graceful shutdown

#### 1.4.5 Config helpers (`sense_common/config.py`)

- [ ] `get_env(key: str, default: str = "") -> str`
- [ ] `get_env_int(key: str, default: int = 0) -> int`
- [ ] `get_env_float(key: str, default: float = 0.0) -> float`
- [ ] `get_env_bool(key: str, default: bool = False) -> bool` (truthy: "true", "1", "yes")
- [ ] `get_env_json(key: str, default: Any = None) -> Any` (parse JSON string from env var)
- [ ] `get_redis_url() -> str` (reads `REDIS_URL`, defaults to `redis://redis:6379`)
- [ ] `get_config_value(redis_config: dict | None, env_key: str, default: Any = None) -> Any` -- reads from Redis config dict first, falls back to env var, then default

### 1.5 Redis configuration

- [ ] Create `redis/redis.conf`:
  ```
  maxmemory 50mb
  maxmemory-policy allkeys-lru
  save ""
  appendonly no
  ```

### 1.6 Validate workspace

- [ ] Run `uv lock` -- verify single lockfile generated
- [ ] Run `uv sync --package sense-common` -- verify common library installs
- [ ] Run `uv sync` -- verify all members install with stub files
- [ ] Run `uv run --package sense-common pytest` -- verify all tests pass

### 1.7 Write tests for sense-common

- [ ] `tests/test_models.py`:
  - SensorReading serialization round-trip
  - Command default request_id generation
  - SourceStatus with error info
- [ ] `tests/test_redis_client.py` (using `fakeredis`):
  - write_readings + read_source round-trip
  - read_all_sources with multiple sources
  - write_status + read_all_statuses
  - publish_data + subscribe verification
  - publish_command + subscribe_commands
  - wait_response with timeout
  - read_config / write_config / seed_config_from_env (NX behavior)
- [ ] `tests/test_ephemeral.py`:
  - Create mock EphemeralSource subclass
  - Verify run() writes readings, status, metadata, publishes
  - Verify run() writes error status on poll failure
- [ ] `tests/test_persistent.py`:
  - Create mock PersistentSource subclass
  - Verify poll loop runs on interval
  - Verify command listener dispatches to handle_command
  - Verify config listener dispatches to on_config_changed
