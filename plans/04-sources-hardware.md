# Phase 4: Hardware Source Services

> **Type:** PARALLEL -- can run after Phase 1 completes.
> **Owner:** `services/source-aranet4/`, `services/source-camera/`
> **Depends on:** Phase 1 (sense-common library).

## Goal

Implement the Aranet4 BLE sensor (ephemeral) and Network Camera (demand-started)
services. Both involve hardware/external process management.

## Reference Code

- `legacy/sense_pulse/devices/aranet4.py` -- BLE device manager
- `legacy/sense_pulse/datasources/aranet4_source.py` -- data source
- `legacy/sense_pulse/devices/network_camera.py` -- FFmpeg/ONVIF device
- `legacy/sense_pulse/datasources/network_camera_source.py` -- data source
- `legacy/sense_pulse/utils/network.py` -- port scanning for camera discovery

---

## Tasks

### 4.1 source-aranet4 (EPHEMERAL)

**Files:**

```
services/source-aranet4/
+-- pyproject.toml
+-- Dockerfile
+-- aranet4_svc/
|   +-- __init__.py
|   +-- main.py
|   +-- source.py
|   +-- scanner.py
+-- tests/
    +-- __init__.py
    +-- test_source.py
    +-- test_scanner.py
```

#### 4.1.1 BLE Scanner (`scanner.py`)

- [ ] Extract from `legacy/devices/aranet4.py`
- [ ] `Aranet4Scanner` class:
  - `async scan(sensors: list[dict], timeout: int = 10) -> dict[str, dict | None]`
  - `sensors` param: list of `{"label": "office", "mac": "AA:BB:CC:DD:EE:FF"}`
  - Uses `aranet4.client._find_nearby()` for passive BLE scanning
  - Callback: match device by MAC, extract readings from advertisement
  - Returns: `{"office": {"co2": 450, "temperature": 22.1, ...}, "bedroom": None}`
  - `None` for sensors not found in scan
  - Replace legacy logging imports with standard `logging`
  - `async discover(timeout: int = 10) -> list[dict]`
  - Passive BLE scan for ANY nearby Aranet4 devices (not filtered by configured MACs)
  - Returns: `[{"name": "Aranet4 12345", "mac": "AA:BB:CC:DD:EE:FF", "rssi": -60}, ...]`
  - Used by scan mode (see 4.1.4)

#### 4.1.2 Source (`source.py`)

- [ ] `Aranet4Source(EphemeralSource)`:
  - `source_id = "co2"`, refresh_interval = 60
  - `async poll(redis)`:
    1. Read config: `config = await read_config(redis, "aranet4")`
    2. Get sensors list: `get_config_value(config, "ARANET4_SENSORS", default=[])`
    3. Get timeout: `get_config_value(config, "ARANET4_TIMEOUT", default=10)`
    4. Create `Aranet4Scanner`, run scan
    5. For each sensor with data: flatten into 5 scalar SensorReadings per sensor:
       - `{label}:co2` (int, unit="ppm")
       - `{label}:temperature` (float, unit="C")
       - `{label}:humidity` (int, unit="%")
       - `{label}:pressure` (float, unit="mbar")
       - `{label}:battery` (int, unit="%")
    6. Skip sensors with `None` (not found in scan)
    7. Return list of SensorReadings
  - Handle: BLE errors, import errors (aranet4 not installed), timeout

#### 4.1.3 Scan mode

The container supports two modes via the `MODE` env var:

- `MODE=poll` (default) -- normal ephemeral poll: read configured sensors, write readings to Redis, exit
- `MODE=scan` -- discovery scan: scan for ANY nearby Aranet4 BLE devices, write results to `scan:co2` Redis key, exit

Triggered by orchestrator via `docker compose run --rm -e MODE=scan source-aranet4`.

- [ ] In scan mode:
  1. Call `scanner.discover(timeout)` to find nearby devices
  2. Write results to `scan:co2` Redis key (JSON list, 60s TTL)
  3. Exit

#### 4.1.4 Entry point, Dockerfile, tests

- [ ] `main.py` -- entry point, reads `MODE` env var to choose poll or scan
- [ ] Dockerfile (try Alpine first, fallback to Debian if BLE doesn't work):
  ```dockerfile
  FROM python:3.12-alpine
  RUN apk add --no-cache bluez bluez-dev gcc musl-dev
  ```
  Container needs: `--privileged` or device mounts (`/dev/hci0`) + D-Bus socket
- [ ] `test_scanner.py`: mock `aranet4.client._find_nearby`, verify scan results + discover results
- [ ] `test_source.py`: mock scanner, verify 5 scalar SensorReadings per sensor, verify Redis writes
- [ ] `test_source.py`: verify scan mode writes discovered devices to `scan:co2` Redis key

---

### 4.2 source-camera (DEMAND-STARTED)

**Files:**

```
services/source-camera/
+-- pyproject.toml
+-- Dockerfile
+-- camera/
|   +-- __init__.py
|   +-- main.py
|   +-- stream.py
|   +-- ptz.py
|   +-- discovery.py
+-- tests/
    +-- __init__.py
    +-- test_stream.py
    +-- test_ptz.py
    +-- test_discovery.py
```

This service supports two modes via the `MODE` env var:

- `MODE=stream` (default) -- demand-started by orchestrator, runs HLS stream, self-terminates on stop
- `MODE=discover` -- ephemeral: scans network for RTSP cameras, writes results to Redis, exits

#### 4.2.1 Stream manager (`stream.py`)

- [ ] Extract from `legacy/devices/network_camera.py`
- [ ] `StreamManager` class:
  - `__init__(rtsp_url, output_dir, transport="tcp")`
  - `async start()` -- build FFmpeg command, spawn subprocess
  - `async stop()` -- terminate FFmpeg gracefully (SIGTERM, then SIGKILL after 5s)
  - `async restart()` -- stop + start
  - `get_status() -> dict` -- return `{status, connected, error, resolution, fps, uptime}`
  - `async monitor()` -- background loop:
    - Check FFmpeg process alive
    - Check HLS playlist freshness (stale if >10s old)
    - Reconnect with exponential backoff on failure
  - Build FFmpeg command: RTSP input -> HLS output (copy video, transcode audio to AAC)
  - Cleanup: remove `.ts` segments and `.m3u8` on stop
  - No thumbnail capture (removed per user request)

#### 4.2.2 PTZ controller (`ptz.py`)

- [ ] Extract from `legacy/devices/network_camera.py`
- [ ] `PTZController` class:
  - `async initialize(host, port, username, password)` -- create ONVIF client
  - `async move(direction, step)` -- send PTZ command
  - Directions: `up`, `down`, `left`, `right`, `zoomin`, `zoomout`
  - ONVIF calls are blocking -- use `ThreadPoolExecutor`
  - `async shutdown()` -- cleanup

#### 4.2.3 Camera discovery (`discovery.py`)

- [ ] Extract from `legacy/utils/network.py`
- [ ] `async discover_cameras(timeout=30) -> list[dict]`
- [ ] TCP port scan on local subnets for ports 554, 8554, 10554
- [ ] Return: `[{"name": "...", "host": "...", "port": 554}]`

#### 4.2.4 Main entry point (`main.py`)

- [ ] Read `MODE` env var (default: `"stream"`)
- [ ] **If `MODE=discover`:**
  1. Run `discover_cameras(timeout)` from `discovery.py`
  2. Write results to `scan:network_camera` Redis key (JSON list, 60s TTL)
  3. Exit (container dies)
- [ ] **If `MODE=stream`:**
  - Read `config:camera` from Redis (fallback to `CAMERA_CONFIG` env)
  - Subscribe to `cmd:network_camera` channel
  - Handle commands:
    - `start` -- start FFmpeg stream, write status to Redis
    - `stop` -- stop FFmpeg, publish `stream:ended`, **exit process** (container self-terminates)
    - `restart` -- stop + start
    - `ptz_move` -- `params.direction`, `params.step`
- [ ] While streaming:
  - Write 6 scalar readings to Redis every 5s: `stream_status` (str), `stream_connected` (bool), `stream_error` (str), `stream_resolution` (str), `stream_fps` (int), `stream_uptime` (float)
  - Run stream monitor in background
- [ ] On FFmpeg process exit (crash/error):
  - Attempt reconnect (up to max attempts)
  - If max attempts reached: publish `stream:ended {reason: "max_reconnects"}`, exit
- [ ] Signal handling for graceful shutdown

#### 4.2.5 Self-termination flow

```
1. User clicks "Stop" in dashboard
2. Gateway publishes cmd:network_camera {action: "stop"}
3. main.py receives command
4. Calls stream_manager.stop() (kills FFmpeg)
5. Publishes stream:ended {reason: "user_stopped"} to Redis
6. Calls sys.exit(0) -- container dies
7. Orchestrator hears stream:ended, runs docker compose cleanup
```

#### 4.2.6 Dockerfile

```dockerfile
FROM python:3.12-alpine
RUN apk add --no-cache ffmpeg
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
# Standard uv install pattern...
```

- [ ] Shared volume: `hls-data` mounted at `/hls` (read-write)

#### 4.2.7 Tests

- [ ] `test_stream.py`:
  - Mock `asyncio.create_subprocess_exec`
  - Verify FFmpeg command construction
  - Verify start/stop/restart lifecycle
  - Verify monitor detects stale stream
  - Verify reconnect logic
- [ ] `test_ptz.py`:
  - Mock ONVIF client
  - Verify direction mapping
- [ ] `test_discovery.py`:
  - Mock TCP connections
  - Verify port scan results
  - Verify discover mode writes found cameras to `scan:network_camera` Redis key

---

## Validation

- [ ] source-aranet4: builds, `uv run --package sense-source-aranet4 pytest` passes
- [ ] source-aranet4: BLE scan works in container on Pi with Bluetooth adapter
- [ ] source-camera: builds, `uv run --package sense-source-camera pytest` passes
- [ ] source-camera: FFmpeg starts, HLS files appear in `/hls` volume
- [ ] source-camera: responds to start/stop commands via Redis
- [ ] source-camera: self-terminates after stop command, publishes `stream:ended`
