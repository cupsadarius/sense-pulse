# Phase 7: SvelteKit 5 Frontend

> **Type:** PARALLEL -- can run after Phase 1 completes.
> **Owner:** `frontend/`
> **Depends on:** Phase 1 (workspace structure), Phase 6 (API shapes -- documented in CONTRACT.md and Phase 6).
> **Note:** Can work in parallel with Phase 6 since API shapes are defined in advance.

## Goal

Build a modern, reactive dashboard using SvelteKit 5 with runes, server load functions,
and WebSocket real-time updates. Gracefully handle missing/unavailable data sources --
the dashboard should render cleanly with 0 to N sources available.

## Stack

- SvelteKit 5 (Svelte 5 runes: `$state`, `$derived`, `$effect`)
- Tailwind CSS 4
- TypeScript strict mode
- `hls.js` (lazy-loaded for camera stream)
- `adapter-node` (lightweight Node server in Docker)

---

## Tasks

### 7.1 Project setup

- [ ] Initialize: `npx sv create frontend` -- SvelteKit 5, TypeScript, Tailwind CSS 4
- [ ] Configure `svelte.config.js`:
  - `adapter-node` for production builds
- [ ] Configure `vite.config.ts`:
  - Proxy `/api` -> `http://localhost:8080` (gateway) for dev
  - Proxy `/ws` -> `ws://localhost:8080` for dev
- [ ] Create `.env` files:
  - `.env.development`: `PUBLIC_API_URL=http://localhost:8080`, `PUBLIC_WS_URL=ws://localhost:8080`
  - `.env.production`: `PUBLIC_API_URL=`, `PUBLIC_WS_URL=` (empty = relative, proxied by Traefik)
- [ ] Configure Tailwind theme:
  ```
  pulse-bg: #0f172a
  pulse-card: #1e293b
  pulse-border: #334155
  pulse-accent: #38bdf8
  ```
- [ ] Install dependencies: `hls.js` (optional/lazy)

### 7.2 TypeScript types (`src/lib/types/`)

- [ ] `sources.ts`:
  ```typescript
  // Uniform reading: always scalar value + unit + timestamp
  export interface SensorReading {
      value: number | string | boolean
      unit: string | null
      timestamp: number
  }
  export interface SourceReadings { [sensorId: string]: SensorReading }

  // Source status from orchestrator/service health
  export interface SourceStatus {
      last_poll: number | null
      last_success: number | null
      last_error: string | null
      poll_count: number
      error_count: number
  }

  // Single source: readings + status merged (from GET /api/sources)
  export interface Source {
      readings: SourceReadings
      status: SourceStatus | null  // null = status TTL expired, unavailable
  }

  // All sources keyed by source_id
  export interface AllSources { [sourceId: string]: Source }

  // Command response (from POST /api/command/{target})
  export interface CommandResult {
      success: boolean
      message: string
      data?: Record<string, any>
  }

  // LED matrix state (from WS /ws/grid)
  export interface MatrixState {
      pixels: number[][]  // 64 elements of [r,g,b]
      mode: string
      rotation: number
      available: boolean
  }

  export type SourceAvailability = 'available' | 'stale' | 'unavailable'
  ```

### 7.3 API client (`src/lib/api/`)

- [ ] `client.ts` -- base fetch wrapper:
  - Configurable base URL from `PUBLIC_API_URL`
  - Add HTTP Basic Auth header from stored credentials
  - Type-safe generic: `api<T>(path, init?) -> Promise<T>`
  - Error class: `ApiError` with status code and message
- [ ] `sources.ts` -- typed read functions:
  - `getSources() -> Promise<AllSources>` -- `GET /api/sources`
  - `getSource(id: string) -> Promise<Source>` -- `GET /api/sources/{id}`
  - `getConfig() -> Promise<ConfigData>` -- `GET /api/config`
- [ ] `commands.ts` -- typed command functions (all use `POST /api/command/{target}`):
  - `sendCommand(target: string, action: string, params?: dict) -> Promise<CommandResult>`
  - Convenience wrappers:
    - `clearDisplay() -> sendCommand("sensors", "clear")`
    - `setRotation(r) -> sendCommand("sensors", "set_rotation", {rotation: r})`
    - `startCamera() -> sendCommand("orchestrator", "start_camera")`
    - `stopCamera() -> sendCommand("orchestrator", "stop_camera")`
    - `ptzMove(dir, step?) -> sendCommand("network_camera", "ptz_move", {direction: dir, step})`
    - `triggerSource(service) -> sendCommand("orchestrator", "trigger", {service})`
    - `scanAranet4() -> sendCommand("orchestrator", "scan_aranet4")`
    - `discoverCameras() -> sendCommand("orchestrator", "discover_cameras")`
  - `updateConfig(sections: Partial<ConfigData>) -> Promise<{status: string, sections_updated: string[]}>` -- `POST /api/config`

### 7.4 WebSocket store (`src/lib/stores/websocket.svelte.ts`)

- [ ] Reactive state using Svelte 5 runes:
  ```typescript
  let connectionStatus = $state<'connecting' | 'connected' | 'disconnected'>('disconnected')
  let sources = $state<AllSources>({})  // same shape as GET /api/sources
  let matrixState = $state<MatrixState | null>(null)
  ```
- [ ] `connect()` function:
  - Open WebSocket to `/ws/sources`
  - Open WebSocket to `/ws/grid`
  - Parse incoming messages, update `sources` state (full snapshot replacement)
  - Set `connectionStatus` on open/close/error
- [ ] Auto-reconnect with exponential backoff: 1s, 2s, 4s, 8s, max 30s
- [ ] Reset backoff on successful connection
- [ ] `disconnect()` -- clean close of both sockets
- [ ] Export reactive state for component consumption

### 7.5 Source availability helper (`src/lib/utils/availability.ts`)

- [ ] `getAvailability(source, expectedInterval) -> SourceAvailability`:
  ```typescript
  export function getAvailability(
      source: Source | undefined,
      expectedInterval: number
  ): SourceAvailability {
      if (!source || !source.status) return 'unavailable'
      if (Object.keys(source.readings).length === 0) return 'unavailable'
      const latest = source.status.last_success
      if (!latest) return 'unavailable'
      const ageSeconds = Date.now() / 1000 - latest
      if (ageSeconds > expectedInterval * 3) return 'stale'
      return 'available'
  }
  ```
- [ ] Expected intervals map:
  - tailscale: 30, pihole: 30, system: 30, sensors: 30, co2: 60, weather: 300

### 7.6 Layout (`src/routes/+layout.svelte`)

- [ ] Dark theme wrapper (`class="dark"` on html)
- [ ] Shared header with:
  - App title + icon
  - WebSocket connection indicator (green/yellow/red dot)
  - Last-updated timestamp
- [ ] Initialize WebSocket on mount, disconnect on destroy
- [ ] Global error boundary

### 7.7 Dashboard page

#### `src/routes/+page.server.ts` (server load function)

- [ ] Fetch initial data from gateway API (SSR):
  ```typescript
  export const load: PageServerLoad = async ({ fetch }) => {
      try {
          const res = await fetch('/api/sources')
          return { sources: res.ok ? await res.json() : {} }
      } catch {
          return { sources: {} }  // gateway down, render empty
      }
  }
  ```
- [ ] Single fetch — `GET /api/sources` returns readings + status merged
- [ ] Dashboard renders even if gateway is down (empty sources object)

#### `src/routes/+page.svelte`

- [ ] Receive server data via `$props()`
- [ ] Merge with WebSocket reactive data:
  ```svelte
  let { data } = $props()
  // WebSocket replaces SSR data once connected
  let sources = $derived(
      Object.keys(websocketStore.sources).length > 0
          ? websocketStore.sources
          : data.sources
  )
  ```
- [ ] Render status grid with source cards
- [ ] Render LED matrix preview
- [ ] Render network camera section (if data available)
- [ ] Render source status bar

### 7.8 Components (`src/lib/components/`)

#### `SourceCard.svelte` -- base card with availability state

- [ ] Props: `sourceId`, `title`, `icon`, `source: Source | undefined`, `expectedInterval: number`
- [ ] Compute availability: `$derived(getAvailability(source, expectedInterval))`
- [ ] Three visual states:
  - **Available:** normal card, green status dot, render children slot
  - **Stale:** yellow border, "Data may be outdated" badge, still render children
  - **Unavailable:** gray/dimmed, "Source offline" text, no data content
- [ ] Snippet/children slot for source-specific content
- [ ] Fade-in animation on state change

#### Individual source cards

Each wraps `SourceCard` and renders source-specific data:

- [ ] `TailscaleCard.svelte`:
  - Show: connected/disconnected badge, peer count
  - Color: green if connected, red if not
- [ ] `PiholeCard.svelte`:
  - Show: queries today (formatted number), blocked count, block percentage
  - Percentage bar visualization
- [ ] `SystemCard.svelte`:
  - Show: CPU%, memory%, load average, CPU temperature
  - Circular gauge or progress bar for CPU/memory
  - Color-code temperature (green <60C, yellow <80C, red >=80C)
- [ ] `SenseHatCard.svelte`:
  - Show: temperature (C), humidity (%), pressure (mbar)
  - Simple value + unit display
- [ ] `Aranet4Card.svelte`:
  - Group flat readings by sensor label (parse `{label}:{metric}` sensor_ids)
  - Show: per-sensor data (one row per sensor label)
  - CO2 color coding: green (<800ppm), yellow (<1200ppm), red (>=1200ppm)
  - Battery level indicator
  - If multiple sensors: tabs or expandable list
  - "Scan for devices" button calls `scanAranet4()`, shows discovered devices
- [ ] `WeatherCard.svelte`:
  - Show: current conditions, temperature, feels-like, wind, humidity
  - Reconstruct 3-day forecast array from `forecast_d{0-2}_*` readings
  - 3-day forecast as mini cards below
  - Weather condition text

#### Interactive components

- [ ] `LedMatrix.svelte`:
  - 8x8 CSS grid of colored cells
  - Updated from `matrixState` WebSocket data
  - Apply rotation offset for web preview
  - Show "Sense HAT unavailable" placeholder when `available: false`
- [ ] `NetworkCamera.svelte`:
  - States: `stopped` -> `starting` -> `streaming` -> `error`
  - Stopped: show "Start Stream" button
  - Starting: show spinner
  - Streaming: HLS.js video player + PTZ controls + "Stop" button
  - Error: show error message + "Retry" button
  - Lazy-load `hls.js` only when entering streaming state
- [ ] `PTZControls.svelte`:
  - Directional pad: up/down/left/right buttons
  - Zoom: zoom-in/zoom-out buttons
  - Each button calls `ptzMove(direction)`
- [ ] `SourceStatusBar.svelte`:
  - Horizontal row of small dots, one per source
  - Color: green (available), yellow (stale), gray (unavailable), red (error)
  - Tooltip on hover with source name + last seen time
- [ ] `ConnectionStatus.svelte`:
  - WebSocket status indicator
  - Dot: green (connected), yellow (connecting), red (disconnected)
  - Label text next to dot

### 7.9 Design system

- [ ] Dark theme: `#0f172a` background, `#1e293b` cards, `#334155` borders
- [ ] Responsive grid:
  - Mobile (< 640px): 1 column
  - Tablet (640-1024px): 2 columns
  - Desktop (> 1024px): 3-4 columns
- [ ] Status colors:
  - Green: `#22c55e` (healthy/connected/available)
  - Yellow: `#eab308` (stale/warning)
  - Red: `#ef4444` (error/disconnected)
  - Gray: `#6b7280` (unavailable/offline)
- [ ] Typography: monospace for values/numbers, sans-serif for labels
- [ ] Animations: fade-in on card appear, smooth transitions on value changes
- [ ] Focus/keyboard accessible interactive elements

### 7.10 Dockerfile

```dockerfile
FROM node:22-alpine AS builder
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM node:22-alpine
WORKDIR /app
COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json .
COPY --from=builder /app/node_modules ./node_modules
ENV PORT=3000
EXPOSE 3000
HEALTHCHECK CMD wget -q --spider http://localhost:3000/ || exit 1
CMD ["node", "build"]
```

### 7.11 Tests

- [ ] Vitest: `SourceCard` renders all 3 availability states correctly
- [ ] Vitest: availability helper returns correct states for edge cases (null, stale, fresh)
- [ ] Vitest: API client formats requests correctly, handles errors
- [ ] Vitest: WebSocket store updates reactive state on message
- [ ] Vitest: WebSocket store reconnects on disconnect
- [ ] Vitest: each source card renders correctly with sample data
- [ ] Vitest: camera component transitions between states correctly

---

## Validation

- [ ] `npm run build` succeeds in `frontend/`
- [ ] `npm run dev` + gateway running -> dashboard shows real data
- [ ] All source cards render correctly in all 3 states (available, stale, unavailable)
- [ ] Dashboard renders cleanly with 0 sources (all unavailable)
- [ ] Dashboard renders cleanly with partial sources (some available, some not)
- [ ] WebSocket auto-reconnects after disconnect
- [ ] LED matrix preview updates in real-time from WebSocket
- [ ] Camera start/stop works through UI
- [ ] Config changes via UI take effect (display rotation, weather location)
- [ ] Responsive: looks good on mobile, tablet, desktop
