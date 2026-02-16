# Phase 3: Sense HAT Service

> **Type:** PARALLEL -- can run after Phase 1 completes.
> **Owner:** `services/source-sensehat/`
> **Depends on:** Phase 1 (sense-common library).

## Goal

Build the most complex service: always-running, reads sensor data, drives the LED
matrix display (cycling through ALL sources read from Redis), handles commands,
and hot-reloads config changes.

## Reference Code

- `legacy/sense_pulse/devices/sensehat.py` -- hardware abstraction
- `legacy/sense_pulse/devices/display.py` -- LED matrix display
- `legacy/sense_pulse/controller.py` -- display cycle controller
- `legacy/sense_pulse/schedule.py` -- sleep schedule
- `legacy/sense_pulse/pi_leds.py` -- Pi onboard LED control
- `legacy/sense_pulse/icons.py` -- 8x8 pixel art icons

## Architecture

This service runs 4 concurrent async tasks:

1. **Sensor poll loop** (every 30s) -- read temp/humidity/pressure, write to Redis
2. **Display cycle loop** -- read ALL sources from Redis, scroll through on LED matrix
3. **Command listener** -- subscribe to `cmd:sensors`, handle clear/rotation/get_matrix
4. **Config listener** -- subscribe to `config:changed`, hot-reload display/sleep settings

Plus a background matrix state publisher (every 500ms).

---

## Tasks

### 3.1 Project structure

```
services/source-sensehat/
+-- pyproject.toml
+-- Dockerfile
+-- sensehat/
|   +-- __init__.py
|   +-- main.py              # Entry point -- runs all 4 tasks
|   +-- source.py            # PersistentSource -- sensor polling
|   +-- display.py           # LED matrix rendering (from legacy display.py)
|   +-- controller.py        # Display cycle controller (from legacy controller.py)
|   +-- icons.py             # 8x8 pixel art (copy from legacy)
|   +-- schedule.py          # Sleep schedule (from legacy schedule.py)
|   +-- pi_leds.py           # Pi onboard LED control (from legacy pi_leds.py)
|   +-- commands.py          # Command handler
+-- tests/
    +-- __init__.py
    +-- test_source.py
    +-- test_controller.py
    +-- test_commands.py
    +-- test_schedule.py
```

### 3.2 Sensor source (`source.py`)

- [ ] Class `SenseHatSensorSource`:
  - `source_id = "sensors"`
  - `async poll(redis) -> list[SensorReading]`:
    1. Get SenseHat instance (lazy init, graceful if unavailable)
    2. Read temp, humidity, pressure via `asyncio.to_thread()` (blocking I/O)
    3. Return 3 SensorReadings: `temperature`, `humidity`, `pressure`
    4. If hardware unavailable: return readings with `value: None`

### 3.3 Display module (`display.py`)

- [ ] Port from `legacy/sense_pulse/devices/display.py`
- [ ] `SenseHatDisplay` class:
  - Constructor takes `SenseHat` instance, rotation, scroll_speed, icon_duration
  - `async show_text(text, color, scroll_speed)` -- run in thread pool
  - `async show_icon(icon_pixels, duration, mode)` -- set pixels, sleep
  - `async show_icon_with_text(icon_name, text, color)` -- icon then scroll
  - `async clear()` -- clear matrix
- [ ] Remove dependency on `sense_pulse.devices.sensehat` module -- use SenseHat instance directly
- [ ] All blocking SenseHat calls wrapped in `asyncio.to_thread()`

### 3.4 Display cycle controller (`controller.py`)

- [ ] Port from `legacy/sense_pulse/controller.py`
- [ ] **Key difference:** reads data from Redis (not in-memory cache)
  ```python
  all_data = await read_all_sources(redis)
  tailscale = all_data.get("tailscale", {})
  pihole = all_data.get("pihole", {})
  # ...
  ```
- [ ] Cycle through sources in order: Tailscale, Pi-hole, System, Sensors, CO2, Weather
- [ ] **Skip sources that have no data in Redis** -- graceful, no crash
- [ ] Use `display.py` for rendering
- [ ] Check sleep schedule before each cycle -- blank display during sleep hours
- [ ] Config values (rotation, scroll_speed, icon_duration) read from instance vars (hot-reloaded)

### 3.5 Icons (`icons.py`)

- [ ] Copy from `legacy/sense_pulse/icons.py` (8x8 pixel art definitions)
- [ ] No changes needed -- pure data file

### 3.6 Sleep schedule (`schedule.py`)

- [ ] Port from `legacy/sense_pulse/schedule.py`
- [ ] `is_sleep_time(start_hour, end_hour) -> bool` -- check if current hour is in sleep window
- [ ] Handle wrap-around (e.g., start=23, end=7)

### 3.7 Pi onboard LEDs (`pi_leds.py`)

- [ ] Port from `legacy/sense_pulse/pi_leds.py`
- [ ] `disable_leds()` / `restore_leds()` -- write to `/sys/class/leds/{PWR,ACT}/{brightness,trigger}`
- [ ] Graceful if sysfs paths don't exist (not running on Pi)

### 3.8 Command handler (`commands.py`)

- [ ] Subscribe to `cmd:sensors` Redis channel
- [ ] Handle commands:
  - `clear` -- clear LED matrix via display, respond `{status: "ok"}`
  - `set_rotation` -- `params.rotation` (0/90/180/270), apply to hardware + update controller, respond ok
  - `get_matrix` -- read current pixel state from hardware, respond with `{data: {pixels: [...]}}`
- [ ] Publish responses to `cmd:sensors:response:{request_id}`

### 3.9 Matrix state publisher

- [ ] Background task running every 500ms
- [ ] Read current pixel state from SenseHat hardware
- [ ] Publish to `matrix:state` channel (see CONTRACT.md for payload format)
- [ ] Include: pixels (64 RGB arrays), mode, rotation, available flag

### 3.10 Config hot-reload

- [ ] Subscribe to `config:changed` channel
- [ ] On `{section: "display"}`:
  - Read `config:display` from Redis
  - Update controller's rotation, scroll_speed, icon_duration
  - Apply rotation to hardware immediately
- [ ] On `{section: "sleep"}`:
  - Read `config:sleep` from Redis
  - Update sleep schedule start/end hours
  - Update `disable_pi_leds` setting

### 3.11 Main entry point (`main.py`)

- [ ] Parse initial config from Redis (with env var fallback)
- [ ] Initialize SenseHat hardware (graceful if unavailable)
- [ ] Create display, controller, command handler instances
- [ ] Run all tasks concurrently:
  ```python
  await asyncio.gather(
      sensor_poll_loop(redis, interval=30),
      display_cycle_loop(redis, controller),
      command_listener(redis),
      config_change_listener(redis),
      matrix_state_publisher(redis),
  )
  ```
- [ ] Signal handling (SIGTERM/SIGINT) for graceful shutdown

### 3.12 Dockerfile (DEBIAN -- required for sense_hat C library)

```dockerfile
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-sense-hat \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
# Standard uv install pattern...
# NOTE: Must use --system-site-packages so venv can access apt-installed sense_hat
```

- [ ] Device mapping in compose: `/dev/i2c-1`
- [ ] Optional: `/sys/class/leds/` mount for Pi LED control

### 3.13 Tests

- [ ] `test_source.py`: mock `sense_hat.SenseHat`, verify 3 sensor readings returned
- [ ] `test_source.py`: test graceful degradation when hardware unavailable (value: None)
- [ ] `test_controller.py`: mock Redis `read_all_sources`, verify display cycle order
- [ ] `test_controller.py`: test skipping missing sources
- [ ] `test_commands.py`: fakeredis pub/sub, verify command handling + responses
- [ ] `test_schedule.py`: test sleep time logic, including wrap-around

---

## Validation

- [ ] Builds on Debian-based Docker image
- [ ] Sensor data appears in Redis when run against real hardware (or mock)
- [ ] LED display cycles through data read from Redis
- [ ] Commands work via Redis pub/sub (clear, set_rotation)
- [ ] Matrix state published to `matrix:state` channel at ~500ms
- [ ] Config changes via Redis take effect without restart
