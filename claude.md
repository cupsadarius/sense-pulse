# Sense Pulse - Development Guide

## Overview
Pi-hole + Tailscale + Sensor monitoring with Raspberry Pi Sense HAT LED display and web dashboard.

**Stack:** Python 3.9+ | FastAPI | AsyncIO | UV package manager

## Package Management (UV)

```bash
uv sync --all-extras --dev    # Install all dependencies
uv run <command>               # Run commands in managed env
```

Lock file: `uv.lock` ensures reproducible builds.

## Architecture

### Data Flow Pattern
```
Data Sources (truth) → DataCache (60s TTL, 30s polling) → API/Display (read-only)
```

**Key Principle:** Data sources hold the truth. Cache polls sources in background. All consumers read from cache (never direct).

### Components
- **AppContext** - Dependency injection container
- **DataCache** - Centralized caching with background polling
- **DataSources** - 6 sources (Pi-hole, Tailscale, System, SenseHat, Aranet4, Weather)
- **StatsDisplay** - LED matrix controller
- **Web App** - FastAPI dashboard with WebSocket updates

### Data Sources Interface
All implement: `fetch_readings()`, `initialize()`, `health_check()`, `shutdown()`

## Pre-Commit Workflow

**Before every commit, run:**
```bash
uv run ruff check --fix src/ tests/   # Lint + autofix
uv run ruff format src/ tests/        # Format
uv run black src/ tests/              # Format (black)
uv run mypy src/                      # Type check
uv run pytest                         # All tests
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
- **Used for:** What the change is used for and where (which components/flows use it)

**Format as concise bullet points** - keep it brief and clear.

## Testing

```bash
uv run pytest                     # Run all tests
uv run pytest --cov=sense_pulse   # With coverage
```

**Config:** `pyproject.toml` - pytest-asyncio, coverage reporting
**Tests:** Cache, DataSources, API, Auth, CLI integration

## Code Quality Tools

- **Ruff** - Fast linter (E, W, F, I, B, C4, UP, ARG, SIM)
- **Black** - Code formatter (line-length: 100)
- **Mypy** - Type checker (lenient, check untyped defs)
- **Pre-commit** - Automated hooks

## CI/CD

GitHub Actions on push/PR:
1. **Lint & Type Check** - Ruff + Black + Mypy
2. **Test Matrix** - Python 3.9-3.12 with coverage
3. **Security Scan** - Bandit

## Development Commands

```bash
# Setup
uv sync --all-extras --dev
uv run pre-commit install

# Run
uv run sense-pulse                # Display + web
uv run sense-pulse --web-only     # Web only
uv run sense-pulse --once -v      # Single cycle debug

# Quality checks
uv run ruff check --fix src/ tests/
uv run black src/ tests/
uv run mypy src/
uv run pytest

# Pre-commit
uv run pre-commit run --all-files
```

## Configuration

`config.yaml` - YAML-based config for all components (Pi-hole, Tailscale, display, web, auth, sensors, cache)

## Key Architecture Decisions

- **Dependency Injection** - AppContext provides all dependencies, no globals
- **Cache-First Reads** - Background polling prevents blocking, instant API responses
- **AsyncIO** - Non-blocking I/O for all operations
- **Separation of Concerns** - DataSource (unified interface) vs Device (low-level wrappers)
