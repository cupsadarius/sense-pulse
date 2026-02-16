# Phase 9: Testing & CI

> **Type:** FINAL -- runs after all parallel phases complete.
> **Owner:** `.github/workflows/`, `.pre-commit-config.yaml`, `README.md`, `CLAUDE.md`
> **Depends on:** All previous phases.

## Goal

Set up testing strategy, CI pipeline, and documentation for the new architecture.

---

## Tasks

### 9.1 CI pipeline (`.github/workflows/ci.yml`)

- [ ] Job: `lint`:
  ```yaml
  steps:
    - uses: astral-sh/setup-uv@v5
    - run: uv run ruff check services/
    - run: uv run ruff format --check services/
    - run: uv run mypy services/
  ```
- [ ] Job: `test-common`:
  ```yaml
  steps:
    - run: uv run --package sense-common pytest
  ```
- [ ] Job: `test-services` (matrix strategy):
  ```yaml
  strategy:
    matrix:
      service:
        - sense-source-weather
        - sense-source-pihole
        - sense-source-ts
        - sense-source-system
        - sense-source-aranet4
        - sense-source-camera
        - sense-gateway
        - sense-orchestrator
  steps:
    - run: uv run --package ${{ matrix.service }} pytest
  ```
- [ ] Job: `test-frontend`:
  ```yaml
  steps:
    - working-directory: frontend
    - run: npm ci && npm test
  ```
- [ ] Job: `docker-build` (verify images build, no push):
  ```yaml
  steps:
    - run: docker compose build
  ```
- [ ] Trigger: push + PR to main

### 9.2 Pre-commit hooks (`.pre-commit-config.yaml`)

- [ ] Update for workspace layout:
  - Ruff check on `services/`
  - Ruff format on `services/`
  - Black on `services/`
  - MyPy on `services/`
- [ ] Add frontend linting (if eslint/prettier configured)

### 9.3 Integration test suite

- [ ] Create `tests/integration/` directory at root
- [ ] `test_data_flow.py`:
  - Start Redis (via testcontainers or docker)
  - Run a source service's `poll()` against fakeredis
  - Verify gateway can read the data
- [ ] `test_command_flow.py`:
  - Simulate command dispatch (gateway -> Redis -> service -> Redis -> gateway)
  - Verify end-to-end via fakeredis
- [ ] `test_config_flow.py`:
  - Write config via gateway endpoint
  - Verify config:changed published
  - Verify source reads updated config

### 9.4 Update README.md

- [ ] Replace monolith documentation with new architecture
- [ ] Add: architecture diagram, service descriptions
- [ ] Add: setup instructions (clone, cp .env.example .env, docker compose up)
- [ ] Add: common operations (view logs, restart service, trigger manual poll)
- [ ] Add: development setup (uv sync, run tests, start individual services)
- [ ] Add: config management (env vars, dashboard config changes, restart requirements)

### 9.5 Update CLAUDE.md

- [ ] Replace monolith dev commands with new workspace commands:
  ```bash
  # Setup
  uv sync

  # Run tests
  uv run --package sense-common pytest
  uv run --package sense-source-weather pytest
  # etc.

  # Lint
  uv run ruff check services/
  uv run ruff format services/

  # Docker
  docker compose build
  docker compose up -d
  docker compose logs -f
  ```
- [ ] Update architecture description
- [ ] Update pre-commit workflow
- [ ] Document plans directory and parallelization guide

### 9.6 Health check documentation

- [ ] Document per-service health check mechanisms
- [ ] Document how source statuses appear in the dashboard
- [ ] Document alert conditions (source overdue = 3x interval)
- [ ] Document orchestrator health monitoring behavior

---

## Validation

- [ ] CI pipeline runs on push/PR and all jobs pass (lint, test, build)
- [ ] Pre-commit hooks catch common issues locally
- [ ] Integration tests verify data + command + config flows
- [ ] README.md accurately describes the new architecture + setup
- [ ] CLAUDE.md has correct dev workflow commands
