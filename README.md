# Sense Pulse

Microservice architecture for monitoring Pi-hole, Tailscale, environmental sensors, and a network camera on a Raspberry Pi, with an 8x8 LED matrix display and a SvelteKit web dashboard.

**Stack:** Python 3.12+ | FastAPI | Redis 7 | UV workspace | SvelteKit 5 | Tailwind CSS 4 | Docker Compose | Traefik v3

## Features

- **Pi-hole Stats**: DNS queries today, ads blocked, block percentage
- **Tailscale Status**: Connection state and online device count
- **Sense HAT Sensors**: Temperature, humidity, atmospheric pressure
- **Aranet4 CO2**: Per-sensor CO2, temperature, humidity, pressure, battery via BLE
- **System Metrics**: CPU usage, memory usage, load average, CPU temperature
- **Weather**: Current conditions and 3-day forecast via wttr.in
- **Network Camera**: RTSP-to-HLS streaming with PTZ control via ONVIF
- **LED Matrix**: 8x8 pixel art display cycling through all stats with sleep schedule
- **Web Dashboard**: Real-time SvelteKit dashboard with WebSocket updates
- **Config Hot-Reload**: Change settings from the dashboard without restarting containers

## Architecture

```
Data Sources ──► Redis (hash + pub/sub) ──► Web Gateway ──► Frontend
                       ▲                         │
                  Orchestrator              Commands / Config
```

Each data source runs as an independent Docker container. Ephemeral sources poll on schedule, write to Redis, and exit. Persistent sources run continuously. All communication happens through Redis.

### Services

| Service | Type | Description |
|---------|------|-------------|
| **source-weather** | Ephemeral | Polls wttr.in for conditions and forecast |
| **source-pihole** | Ephemeral | Polls Pi-hole API for DNS stats |
| **source-tailscale** | Ephemeral | Polls Tailscale daemon for connection status |
| **source-system** | Ephemeral | Reads CPU, memory, load, temp from `/proc` and `/sys` |
| **source-aranet4** | Ephemeral | Reads Aranet4 sensors via BLE; supports scan-based discovery |
| **source-sensehat** | Persistent | Reads onboard sensors, drives LED matrix, publishes matrix state |
| **source-camera** | Demand | RTSP-to-HLS via FFmpeg with ONVIF PTZ and network discovery |
| **orchestrator** | Persistent | Schedules polls, dispatches commands, seeds config |
| **web-gateway** | Persistent | FastAPI REST + WebSocket gateway |
| **frontend** | Persistent | SvelteKit 5 dashboard |

### Docker Compose Profiles

- **Default** (no profile): redis, traefik, web-gateway, frontend, orchestrator, source-sensehat
- **`poll`**: source-tailscale, source-pihole, source-system, source-aranet4, source-weather
- **`camera`**: source-camera

Idle RAM usage is ~130 MB (6 always-on containers), leaving ~870 MB on a 1 GB Pi for ephemeral bursts and FFmpeg.

## Prerequisites

- Raspberry Pi 3B+ (or compatible) with Docker installed
- Sense HAT V1 (optional -- dashboard works without hardware)
- Pi-hole installed and running
- Tailscale installed and configured

## Quick Start

```bash
# Clone the repository
git clone https://github.com/cupsadarius/sense-pulse.git
cd sense-pulse

# Copy and configure environment
cp .env.example .env
nano .env

# Build and start
make build
make up
```

The dashboard will be available at `http://<your-pi-ip>` (Traefik routes on port 80).

## Configuration

All configuration is via environment variables in `.env`. The orchestrator seeds these into Redis on first boot (using `SET NX`, so dashboard changes are preserved across restarts).

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://redis:6379` | Redis connection URL |
| `PIHOLE_HOST` | `http://pi.hole` | Pi-hole URL |
| `PIHOLE_PASSWORD` | | Pi-hole app password |
| `WEATHER_LOCATION` | | Location for wttr.in (empty = auto-detect) |
| `ARANET4_SENSORS` | `[]` | JSON array: `[{"label":"office","mac":"AA:BB:..."}]` |
| `ARANET4_TIMEOUT` | `10` | BLE scan timeout (seconds) |
| `CAMERA_CONFIG` | `[]` | JSON camera config array |
| `DISPLAY_ROTATION` | `0` | LED rotation (0, 90, 180, 270) |
| `SCROLL_SPEED` | `0.08` | LED text scroll speed |
| `ICON_DURATION` | `1.5` | LED icon display duration (seconds) |
| `SLEEP_START` | `23` | Hour to blank display |
| `SLEEP_END` | `7` | Hour to resume display |
| `DISABLE_PI_LEDS` | `false` | Turn off Pi onboard LEDs during sleep |
| `SCHEDULE_TAILSCALE` | `30` | Poll interval in seconds |
| `SCHEDULE_PIHOLE` | `30` | Poll interval in seconds |
| `SCHEDULE_SYSTEM` | `30` | Poll interval in seconds |
| `SCHEDULE_ARANET4` | `60` | Poll interval in seconds |
| `SCHEDULE_WEATHER` | `300` | Poll interval in seconds |
| `AUTH_ENABLED` | `true` | Enable HTTP Basic Auth on API |
| `AUTH_USERNAME` | `admin` | Auth username |
| `AUTH_PASSWORD_HASH` | | Bcrypt password hash |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/sources` | All source readings + status |
| GET | `/api/sources/{id}` | Single source data |
| GET | `/api/config` | All config sections |
| POST | `/api/config` | Partial config update |
| POST | `/api/command/{target}` | Dispatch command to a service |
| GET | `/api/stream/{path}` | Serve HLS playlist and segments |
| GET | `/health` | Gateway + Redis health check |
| WS | `/ws/sources` | Real-time source data (batched) |
| WS | `/ws/grid` | LED matrix state (500ms) |

## Make Targets

```bash
make up          # Start all always-on services
make down        # Stop all services
make logs        # Follow all container logs
make build       # Build all Docker images
make restart     # Restart all services
make status      # Show container status
make test-poll   # Test-run an ephemeral poll
make shell-redis # Open Redis CLI
```

## Development

### Setup

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all workspace packages + dev dependencies
uv sync --dev --all-packages

# Install pre-commit hooks
uv run pre-commit install

# Install frontend dependencies
cd frontend && npm ci
```

### Running Tests

```bash
# All services
uv run pytest

# Individual service
uv run pytest services/common/tests/ -v
uv run pytest services/web-gateway/tests/ -v

# Frontend type checking
cd frontend && npm run check
```

### Code Quality

```bash
# Lint
uv run ruff check services/
uv run ruff check --fix services/

# Format
uv run ruff format services/

# Type check (common library)
uv run mypy services/common/sense_common/

# All pre-commit hooks
uv run pre-commit run --all-files
```

### Project Structure

```
sense-pulse/
├── docker-compose.yml          # Service topology and profiles
├── .env.example                # Environment configuration template
├── Makefile                    # Common operations
├── pyproject.toml              # UV workspace root + dev deps
├── uv.lock                    # Reproducible dependency lock
├── traefik/                    # Traefik reverse proxy config
├── redis/                      # Redis configuration
├── frontend/                   # SvelteKit 5 dashboard
│   ├── src/lib/components/     # Svelte components
│   ├── src/lib/stores/         # WebSocket state management
│   └── src/routes/             # SvelteKit routes
└── services/
    ├── common/                 # Shared library (sense-common)
    │   ├── sense_common/       # Models, base classes, Redis client, config
    │   └── tests/
    ├── orchestrator/           # Service lifecycle + scheduling
    ├── web-gateway/            # FastAPI REST + WebSocket gateway
    ├── source-weather/         # Weather polling
    ├── source-pihole/          # Pi-hole polling
    ├── source-tailscale/       # Tailscale polling
    ├── source-system/          # System metrics polling
    ├── source-sensehat/        # Sense HAT sensors + LED display
    ├── source-aranet4/         # Aranet4 CO2 via BLE
    └── source-camera/          # RTSP-to-HLS + ONVIF PTZ
```

### CI/CD

GitHub Actions on push to `main`/`feature/*` and PRs to `main`:

1. **Lint & Type Check** -- ruff check + format + mypy on `services/`
2. **Test Common** -- `services/common/tests/`
3. **Test Services** -- Matrix of all 9 services (depends on common passing)
4. **Build Frontend** -- `npm ci && npm run check && npm run build`

## License

MIT License
