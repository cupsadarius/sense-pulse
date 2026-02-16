# Phase 8: Docker Compose + Traefik

> **Type:** FINAL -- runs after all parallel phases (2-7) complete.
> **Owner:** `docker-compose.yml`, `.dockerignore`, `.env.example`, `traefik/`
> **Depends on:** All previous phases.

## Goal

Wire all services together into a working `docker compose up` that runs the
full stack on a Raspberry Pi 3B.

---

## Tasks

### 8.1 docker-compose.yml

- [ ] Write complete compose file with all services
- [ ] Define network: `internal` (bridge, for all service communication)
- [ ] Define volume: `hls-data` (shared between source-camera and web-gateway)
- [ ] Use compose profiles:
  - **Default** (no profile): redis, traefik, web-gateway, frontend, orchestrator, source-sensehat
  - **`poll`** profile: all ephemeral sources (orchestrator triggers them with `--profile poll`)
  - **`camera`** profile: source-camera (demand-started by orchestrator)
- [ ] All services use project root as build context, individual Dockerfile paths

#### Service definitions

**redis:**
- [ ] Image: `redis:7-alpine`
- [ ] Command: `redis-server /etc/redis/redis.conf`
- [ ] Volume: `./redis/redis.conf:/etc/redis/redis.conf:ro`
- [ ] Network: `internal`
- [ ] Health check: `redis-cli ping`
- [ ] `mem_limit: 64m`
- [ ] `restart: unless-stopped`

**traefik:**
- [ ] Image: `traefik:v3`
- [ ] `network_mode: host` (sees Tailscale interface)
- [ ] Volumes: `/var/run/docker.sock:/var/run/docker.sock:ro`, `./traefik:/etc/traefik:ro`
- [ ] `mem_limit: 64m`
- [ ] `restart: unless-stopped`

**web-gateway:**
- [ ] Build: `context: .`, `dockerfile: services/web-gateway/Dockerfile`
- [ ] `depends_on: [redis]`
- [ ] Volumes: `hls-data:/hls:ro`
- [ ] Network: `internal`
- [ ] Labels: Traefik routing for `/api/*` and `/ws/*`
- [ ] `env_file: .env`
- [ ] `mem_limit: 96m`
- [ ] `restart: unless-stopped`
- [ ] Health check: `wget -q --spider http://localhost:8080/health`

**frontend:**
- [ ] Build: `context: .`, `dockerfile: frontend/Dockerfile`
- [ ] Network: `internal`
- [ ] Labels: Traefik routing for `/*`
- [ ] `mem_limit: 48m`
- [ ] `restart: unless-stopped`
- [ ] Health check: `wget -q --spider http://localhost:3000/`

**orchestrator:**
- [ ] Build: `context: .`, `dockerfile: services/orchestrator/Dockerfile`
- [ ] `depends_on: [redis]`
- [ ] Volumes: `/var/run/docker.sock:/var/run/docker.sock`
- [ ] Network: `internal`
- [ ] `env_file: .env`
- [ ] `mem_limit: 32m`
- [ ] `restart: unless-stopped`

**source-sensehat:**
- [ ] Build: `context: .`, `dockerfile: services/source-sensehat/Dockerfile`
- [ ] `depends_on: [redis]`
- [ ] `privileged: true` (or `devices: [/dev/i2c-1]`)
- [ ] Network: `internal`
- [ ] `env_file: .env`
- [ ] `mem_limit: 64m`
- [ ] `restart: unless-stopped`

**source-tailscale** (profile: poll):
- [ ] Build: `context: .`, `dockerfile: services/source-tailscale/Dockerfile`
- [ ] `profiles: [poll]`
- [ ] Volumes: `/var/run/tailscale/tailscaled.sock:/var/run/tailscale/tailscaled.sock:ro`
- [ ] Network: `internal`
- [ ] `env_file: .env`
- [ ] `mem_limit: 48m`
- [ ] `restart: no`

**source-pihole** (profile: poll):
- [ ] Build + profiles + network + env_file + mem_limit: 48m + restart: no

**source-system** (profile: poll):
- [ ] Volumes: `/proc:/host/proc:ro`, `/sys:/host/sys:ro`
- [ ] + standard poll profile config

**source-aranet4** (profile: poll):
- [ ] `privileged: true`
- [ ] Volumes: `/var/run/dbus:/var/run/dbus:ro`
- [ ] + standard poll profile config

**source-weather** (profile: poll):
- [ ] Standard poll profile config (no special mounts)

**source-camera** (profile: camera):
- [ ] `profiles: [camera]`
- [ ] Volumes: `hls-data:/hls`
- [ ] Network: `internal`
- [ ] `env_file: .env`
- [ ] `mem_limit: 128m` (FFmpeg needs headroom)
- [ ] `restart: no`

### 8.2 Traefik config (`traefik/traefik.yml`)

- [ ] Docker provider: `exposedByDefault: false`
- [ ] Entrypoints: `web` (:80), `websecure` (:443)
- [ ] API dashboard enabled (insecure -- only on Tailnet)
- [ ] Log level: `WARN`
- [ ] Document Tailscale HTTPS options:
  - Option A: `tailscale cert` on host, mount certs
  - Option B: HTTP-only on Tailnet (Tailscale encrypts transport anyway) -- recommended for Pi

### 8.3 Service routing labels

- [ ] Frontend: `traefik.http.routers.frontend.rule=PathPrefix('/')`
- [ ] Frontend: `traefik.http.routers.frontend.priority=1` (lowest priority, catch-all)
- [ ] Gateway API: `traefik.http.routers.api.rule=PathPrefix('/api')` with `priority=10`
- [ ] Gateway WebSocket: `traefik.http.routers.ws.rule=PathPrefix('/ws')` with `priority=10`

### 8.4 .env.example

- [ ] Write complete template with ALL environment variables from CONTRACT.md
- [ ] Group by section with comments
- [ ] Include sensible defaults

### 8.5 .dockerignore

- [ ] Write:
  ```
  .git
  .venv
  .mypy_cache
  .ruff_cache
  .pytest_cache
  .coverage
  htmlcov
  coverage.json
  legacy
  __pycache__
  *.pyc
  .env
  node_modules
  frontend/.svelte-kit
  ```

### 8.6 Logging config (all services)

- [ ] Set `logging.driver: json-file` with options:
  - `max-size: 10m`
  - `max-file: 3`

### 8.7 Makefile (convenience commands)

- [ ] `make up` -- `docker compose up -d`
- [ ] `make down` -- `docker compose down`
- [ ] `make logs` -- `docker compose logs -f`
- [ ] `make build` -- `docker compose build`
- [ ] `make restart` -- `docker compose restart`
- [ ] `make status` -- `docker compose ps`
- [ ] `make test-poll` -- `docker compose --profile poll run --rm source-weather`

---

## Validation

- [ ] `docker compose build` -- all images build successfully
- [ ] `docker compose up -d` -- core services start (redis, traefik, gateway, frontend, orchestrator, sensehat)
- [ ] `docker compose --profile poll run --rm source-weather` -- ephemeral source runs + writes to Redis
- [ ] Dashboard loads at `http://<pi-ip>` and shows data
- [ ] Orchestrator triggers all ephemeral sources on boot
- [ ] WebSocket updates work through Traefik
- [ ] Camera demand-start works (start -> stream -> stop -> container dies)
- [ ] Config changes via dashboard take effect
- [ ] Memory usage stays under ~200MB idle on Pi 3B
- [ ] Access works from another device on Tailnet
