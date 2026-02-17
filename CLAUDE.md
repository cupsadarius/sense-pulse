# Sense Pulse - Development Guide

## Overview

Microservice architecture for Pi-hole, Tailscale, and sensor monitoring with a SvelteKit web dashboard. Each data source runs as an independent service communicating via Redis pub/sub and hash storage.

**Stack:** Python 3.12+ | FastAPI | Redis | UV workspace | SvelteKit | Docker

## Package Management (UV Workspace)

The project uses a UV workspace with all services under `services/`.

```bash
uv sync --dev                  # Install all workspace packages + dev deps
uv run <command>               # Run commands in managed env
```

Workspace members are defined in the root `pyproject.toml` under `[tool.uv.workspace]`.
Lock file: `uv.lock` ensures reproducible builds.

## Architecture

### Data Flow Pattern
```
Data Sources → Redis (hash + pub/sub) → Web Gateway → Frontend
                  ↑                         ↓
            Orchestrator              Commands / Config
```

**Key Principle:** Each source service independently polls its data source and writes to Redis. The web gateway reads from Redis and serves the frontend. The orchestrator manages service lifecycle and health.

### Services (`services/`)
| Service | Description |
|---------|-------------|
| **common** | Shared library (`sense-common`): Redis client, base service, models, config |
| **source-weather** | OpenWeatherMap polling |
| **source-pihole** | Pi-hole API polling |
| **source-tailscale** | Tailscale API polling |
| **source-system** | System metrics (CPU, memory, disk, temp) |
| **source-sensehat** | Raspberry Pi Sense HAT sensors + LED display |
| **source-aranet4** | Aranet4 CO2 sensor via BLE |
| **source-camera** | ONVIF camera snapshots |
| **orchestrator** | Service health monitoring, command dispatch |
| **web-gateway** | FastAPI REST/WebSocket gateway for the frontend |

### Frontend (`frontend/`)
SvelteKit dashboard served by the web gateway.

### Legacy (`legacy/`)
Original monolith code preserved for reference. Not used in production.

## Pre-Commit Workflow

**Before every commit, run:**
```bash
uv run ruff check --fix services/   # Lint + autofix
uv run ruff format services/        # Format
uv run mypy services/common/sense_common/  # Type check common library
uv run pytest                        # All tests
```

**Or use pre-commit hooks:**
```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

## End Summary (After Commit)

**After committing changes, generate a diff summary vs main:**

```bash
git fetch origin
git diff origin/main --stat           # Overview of changes
git diff origin/main --name-only      # List changed files
git diff origin/main <file>           # Detailed diff per file
```

**For each changed file, provide:**
- **What:** Brief description of the change
- **Why:** Reason for the change
- **Used where:** Which components/flows use this change

**Format as concise bullet points** - keep it brief and clear.

## Testing

```bash
# Test all services
uv run pytest

# Test individual services
uv run pytest services/common/tests/ -v
uv run pytest services/source-weather/tests/ -v
uv run pytest services/source-pihole/tests/ -v
uv run pytest services/source-tailscale/tests/ -v
uv run pytest services/source-system/tests/ -v
uv run pytest services/source-sensehat/tests/ -v
uv run pytest services/source-aranet4/tests/ -v
uv run pytest services/source-camera/tests/ -v
uv run pytest services/orchestrator/tests/ -v
uv run pytest services/web-gateway/tests/ -v
```

**Config:** `pyproject.toml` - pytest-asyncio, test paths set to `services/*/tests`

## Code Quality Tools

- **Ruff** - Fast linter + formatter (E, W, F, I, B, C4, UP, ARG, SIM)
- **Mypy** - Type checker (common library)
- **Pre-commit** - Automated hooks (ruff, trailing whitespace, YAML/JSON/TOML checks)

## CI/CD

GitHub Actions on push to `main`/`feature/*` and PRs to `main`:
1. **Lint & Type Check** - Ruff check + format + Mypy on `services/`
2. **Test Common** - `services/common/tests/`
3. **Test Services** - Matrix of all 9 services (depends on common passing)
4. **Build Frontend** - `npm ci && npm run build` in `frontend/`

## Development Commands

```bash
# Setup
uv sync --dev
uv run pre-commit install

# Lint
uv run ruff check services/
uv run ruff check --fix services/
uv run ruff format services/
uv run mypy services/common/sense_common/

# Test
uv run pytest                                    # All tests
uv run pytest services/common/tests/ -v          # Common library
uv run pytest services/source-weather/tests/ -v  # Single service

# Frontend
cd frontend && npm ci && npm run build

# Pre-commit
uv run pre-commit run --all-files
```

## Configuration

Each service reads configuration from environment variables. Redis connection details are shared across all services. See individual service `pyproject.toml` files for dependencies.

## Key Architecture Decisions

- **Microservices** - Each data source is an independent service with its own process
- **Redis Data Bus** - Pub/sub for events, hashes for current state, decouples all services
- **UV Workspace** - Single lock file, shared dev dependencies, per-service packages
- **Cache-Free Reads** - Gateway reads directly from Redis (Redis is the cache)
- **Independent Deployment** - Each service can be built/deployed separately via Docker
