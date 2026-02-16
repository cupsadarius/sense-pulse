# Phase 0: Architecture Overview

## Project

Decompose the Sense Pulse monolith into a microservice architecture running on Docker
(Raspberry Pi 3B, 1GB RAM), with a SvelteKit 5 frontend, Redis data bus, and Traefik
reverse proxy exposed via Tailscale.

## Current State

- Single Python process on bare metal Raspberry Pi
- In-memory DataCache polls 7 data sources every 30s
- FastAPI serves Jinja2 HTML templates + WebSocket streams
- Config via YAML file on disk
- Tight coupling between hardware (Sense HAT, BLE, FFmpeg) and web layer

## Target State

```
                         Tailnet
                           |
                      +---------+
                      | Traefik |  (host network)
                      +----+----+
                           |
                 +---------+---------+
                 |         |         |
           +-----+---+ +--+----+ +--+-----+
           |SvelteKit| |  API  | |  HLS   |
           |Frontend | |  GW   | | volume |
           |(static) | | (Py)  | |(files) |
           +---------+ +--+----+ +--------+
                           |
                      +----+----+
                      |  Redis  |
                      +----+----+
                           |
       +-------+-------+--+--+--------+--------+
       |       |       |     |        |        |
     +-+-+  +--+-+  +--++  +-+-+ +----+-+ +---+---+
     |TS |  |Pi- |  |Sys|  |SH | |AR4   | |Camera |
     |   |  |hole|  |   |  |   | |(BLE) | |(FFmp) |
     +---+  +----+  +---+  +---+ +------+ +-------+
    ephem   ephem   ephem  always  ephem    demand
```

## Service Classification

| Service          | Pattern        | Base Image      | Privileged/Devices        | Est. RAM |
|------------------|----------------|-----------------|---------------------------|----------|
| redis            | Always running | redis:7-alpine  | No                        | ~5MB     |
| traefik          | Always running | traefik:v3      | Host network              | ~30MB    |
| web-gateway      | Always running | Alpine + Python | No                        | ~40MB    |
| frontend         | Always running | Alpine + Node   | No                        | ~15MB    |
| orchestrator     | Always running | Alpine + Python | Docker socket             | ~10MB    |
| source-sensehat  | Always running | Debian Bookworm | /dev/i2c-1                | ~30MB    |
| source-tailscale | Ephemeral      | Alpine + Python | Tailscale socket mount    | ~15MB*   |
| source-pihole    | Ephemeral      | Alpine + Python | No                        | ~15MB*   |
| source-system    | Ephemeral      | Alpine + Python | /proc, /sys (read-only)   | ~15MB*   |
| source-aranet4   | Ephemeral      | Alpine + Python | Privileged (BLE + D-Bus)  | ~20MB*   |
| source-weather   | Ephemeral      | Alpine + Python | No                        | ~15MB*   |
| source-camera    | Demand-start   | Alpine + FFmpeg | No                        | ~20MB*   |

*Ephemeral services only consume RAM during their brief poll cycle.

**Idle total: ~130MB** (5 always-running + redis + traefik). Leaves ~870MB for OS + ephemeral bursts + FFmpeg.

## Data Flow

### Source Polling (ephemeral)

```
Orchestrator triggers container
  -> Source starts
  -> Reads config from Redis (config:{section})
  -> Polls external data source
  -> Writes readings to Redis (source:{id}:{sensor}, TTL 60s)
  -> Writes status to Redis (status:{id}, TTL 120s)
  -> Publishes to data:{id} channel
  -> Container exits
```

### Web Reads

```
Browser -> SvelteKit -> API Gateway -> Redis GET -> JSON response
Browser -> SvelteKit -> WebSocket -> Gateway subscribes Redis pub/sub -> push updates
```

### Commands (hardware control)

```
Browser -> SvelteKit -> API Gateway -> Redis PUBLISH cmd:{service}
  -> Service executes command
  -> Redis PUBLISH cmd:{service}:response:{request_id}
  -> Gateway returns response to browser
```

### Camera Streaming (demand-start)

```
User clicks "Start Stream"
  -> Gateway -> PUBLISH cmd:orchestrator {start_camera}
  -> Orchestrator starts source-camera container
  -> source-camera reads config:camera from Redis
  -> Spawns FFmpeg, writes HLS to shared volume
  -> Gateway serves HLS files from shared volume

User clicks "Stop Stream"
  -> Gateway -> PUBLISH cmd:network_camera {stop}
  -> source-camera stops FFmpeg
  -> Publishes stream:ended event
  -> Container self-terminates
  -> Orchestrator cleans up container
```

### Dynamic Config Changes

```
User changes setting in dashboard
  -> Gateway writes to Redis config:{section}
  -> Gateway publishes config:changed {section}
  -> Persistent services (sensehat) hot-reload immediately
  -> Ephemeral sources pick up changes on next poll cycle
  -> No restarts needed
```

## Parallelization Guide

```
Phase 1 (foundation) ---- SEQUENTIAL, must complete first
        |
        +-- Phase 2 (simple sources)      -- Agent B: services/source-{weather,pihole,tailscale,system}/
        +-- Phase 3 (sensehat)            -- Agent C: services/source-sensehat/
        +-- Phase 4 (hardware sources)    -- Agent D: services/source-{aranet4,camera}/
        +-- Phase 5 (orchestrator)        -- Agent E: services/orchestrator/
        +-- Phase 6 (web gateway)         -- Agent F: services/web-gateway/
        +-- Phase 7 (SvelteKit frontend)  -- Agent G: frontend/
                |
                +-- Phase 8 (docker + traefik)  -- Agent H
                +-- Phase 9 (testing + CI)      -- Agent I
```

## Rules for Parallel Agents

1. Each agent ONLY writes files in its owned directory (listed in each phase doc)
2. Each agent reads `plans/CONTRACT.md` for the Redis API contract
3. Each agent imports from `sense_common` -- do NOT modify `services/common/`
4. If you need something added to `sense_common`, add a `## Requested sense-common Changes` section at the bottom of your phase plan
5. No agent touches `pyproject.toml` at the workspace root (Phase 1 owns it)
6. No agent touches `docker-compose.yml` (Phase 8 owns it)

## File Ownership Map

| Directory / File                | Owner   |
|---------------------------------|---------|
| `pyproject.toml` (root)        | Phase 1 |
| `uv.lock`                      | Phase 1 |
| `services/common/`             | Phase 1 |
| `redis/`                       | Phase 1 |
| `legacy/`                      | Phase 1 |
| `services/source-weather/`     | Phase 2 |
| `services/source-pihole/`      | Phase 2 |
| `services/source-tailscale/`   | Phase 2 |
| `services/source-system/`      | Phase 2 |
| `services/source-sensehat/`    | Phase 3 |
| `services/source-aranet4/`     | Phase 4 |
| `services/source-camera/`      | Phase 4 |
| `services/orchestrator/`       | Phase 5 |
| `services/web-gateway/`        | Phase 6 |
| `frontend/`                    | Phase 7 |
| `docker-compose.yml`           | Phase 8 |
| `.dockerignore`                | Phase 8 |
| `.env.example`                 | Phase 8 |
| `traefik/`                     | Phase 8 |
| `.github/workflows/`           | Phase 9 |
| `.pre-commit-config.yaml`      | Phase 9 |
| `README.md`                    | Phase 9 |
| `CLAUDE.md`                    | Phase 9 |
