# Changelog

## Version 0.9.0 - Unified DataSource Interface (Breaking Changes)

### Major Refactoring

**Unified DataSource Interface**
- Introduced standardized `DataSource` abstract base class for all data sources
- All data sources (Pi-hole, Tailscale, System Stats, Sense HAT, Aranet4) now implement consistent interface
- Single `MockDataSource` class for testing all sources
- Improved type safety with `SensorReading` and `DataSourceMetadata` classes

### Breaking Changes

⚠️ **API Changes**
- Cache keys renamed for clarity:
  - `"sensors"` → `"sensehat"` (Sense HAT onboard sensors)
  - `"co2"` → `"aranet4"` (Aranet4 CO2 sensors)
- Removed `cache.register_source(key, callable)` - use `cache.register_data_source(source)` instead
- All DataSource objects must implement 5 required methods:
  - `initialize()` - Setup and authentication
  - `fetch_readings()` - Fetch fresh data (no internal caching)
  - `get_metadata()` - Return source configuration
  - `health_check()` - Verify availability
  - `shutdown()` - Clean up resources

### New Features

**DataSource Architecture:**
- `src/sense_pulse/datasources/base.py` - Core interfaces
- `src/sense_pulse/datasources/pihole_source.py` - Pi-hole wrapper
- `src/sense_pulse/datasources/tailscale_source.py` - Tailscale wrapper
- `src/sense_pulse/datasources/system_source.py` - System metrics wrapper
- `src/sense_pulse/datasources/sensehat_source.py` - Sense HAT wrapper
- `src/sense_pulse/datasources/aranet4_source.py` - Aranet4 wrapper
- `src/sense_pulse/datasources/registry.py` - Source management

**Testing Improvements:**
- `tests/mock_datasource.py` - Reusable mock for all tests
- `tests/test_datasources.py` - Comprehensive test suite (17 tests)
- 73% cache coverage, improved testability across board

### Migration Guide

**If you're using the cache API directly:**

```python
# OLD - No longer works
cache.register_source("custom", my_fetch_function)

# NEW - Implement DataSource interface
from sense_pulse.datasources import DataSource, DataSourceMetadata, SensorReading

class CustomDataSource(DataSource):
    async def initialize(self): ...
    async def fetch_readings(self): ...
    def get_metadata(self): ...
    async def health_check(self): ...
    async def shutdown(self): ...

cache.register_data_source(CustomDataSource())
```

**If you're accessing cache data:**

```python
# OLD
sensors = await cache.get("sensors")
co2_data = await cache.get("co2")

# NEW
sensors = await cache.get("sensehat")
co2_data = await cache.get("aranet4")
```

### Files Changed

- `src/sense_pulse/cache.py` - Removed legacy support, DataSource-only
- `src/sense_pulse/web/app.py` - Initialize all DataSource objects
- `src/sense_pulse/web/routes.py` - Updated cache keys throughout
- `src/sense_pulse/datasources/*` - New unified architecture
- `tests/test_datasources.py` - New comprehensive tests

### Upgrade Instructions

```bash
# Pull latest changes
git pull origin main

# Restart service
sudo systemctl restart sense-pulse
```

**Note:** This is a breaking change. If you have custom code accessing the cache or registering data sources, you'll need to update it according to the migration guide above.

---

## Version 0.8.1 - Aranet4 Enhancements and Web Display Fixes

### Bug Fixes

**Aranet4 Display Rendering**
- Fixed issue where Aranet sensor data was only shown in web client but not on physical display
- Display now checks for cached data instead of sensor configuration status
- Ensures consistent behavior between web and physical display

**Web Grid Icon Rotation**
- Fixed double-rotation bug in web LED matrix preview
- Icons now display with correct orientation matching physical display
- Web preview only applies offset rotation, not physical rotation (which is already applied by Sense HAT)

### Enhancements

**Complete Aranet4 Sensor Display**
- Physical display now shows temperature, CO2, and humidity from Aranet4 sensors
- Previously only showed CO2 levels
- All three metrics displayed with appropriate icons and colors
- Dynamically handles any configured sensor labels (office, bedroom, etc.)

### Technical Changes

**Controller Updates:**
- `display_co2_levels()` renamed conceptually to display all Aranet data (temp, CO2, humidity)
- Method now iterates dynamically over all sensors in cache
- Removed hardcoded sensor labels (office/bedroom)
- Uses existing thermometer and water_drop icons for temp/humidity

**Web Template Updates:**
- Fixed `rotateIndex()` function to only apply web offset rotation
- Removed double-rotation issue where physical rotation was added to already-rotated pixels
- Added comment explaining rotation logic for future maintenance

### Files Changed

- `src/sense_pulse/controller.py` - Enhanced Aranet display, fixed cache check
- `src/sense_pulse/web/templates/index.html` - Fixed icon rotation calculation

### Migration from v0.8.0

No configuration changes required! Simply restart the service:

```bash
sudo systemctl restart sense-pulse
```

The display will now show temperature, CO2, and humidity from Aranet sensors, and the web preview will display icons with correct rotation.

---

## Version 0.8.0 - WebSocket Real-Time Dashboard

### Major Changes

**Removed HTMX - Pure WebSocket Architecture**
- Completely removed HTMX dependency from the project
- All dashboard updates now stream via WebSocket at 500ms intervals
- Zero HTTP polling overhead after initial page load
- Single unified `/ws/dashboard` endpoint for all data

**Real-Time Updates**
- Dashboard updates every 500ms (10x faster than previous 5-second polling)
- LED matrix preview included in the same WebSocket stream
- Smooth progress bar animations for CPU and memory usage
- Live timestamp updates showing exact last update time

**Simplified Frontend**
- Vanilla JavaScript for DOM updates (no framework dependencies)
- Direct element manipulation via added IDs to status cards
- Maintained server-side Jinja2 rendering for initial page load
- Graceful WebSocket reconnection with visual status indicator

### Technical Changes

**Removed Endpoints:**
- `/ws/matrix` - Replaced by unified `/ws/dashboard`
- `/api/matrix` - No longer needed (data in WebSocket)

**New Endpoints:**
- `/ws/dashboard` - Unified WebSocket streaming all sensor data + LED matrix

**WebSocket Data Structure:**
```json
{
  "tailscale": {...},
  "pihole": {...},
  "system": {...},
  "sensors": {...},
  "co2": {...},
  "matrix": {
    "pixels": [...],
    "mode": "...",
    "rotation": 0,
    "web_offset": 90
  },
  "hardware": {...},
  "config": {...}
}
```

**Template Updates:**
- Removed all `hx-*` attributes from templates
- Added element IDs for JavaScript DOM updates
- Button actions converted to vanilla `fetch()` calls
- Initial render includes cached data from server

**Routes Changes:**
- `index()` route now passes all cached data for initial render
- Dashboard WebSocket sends complete state every 500ms
- Removed legacy compatibility endpoints

### Files Changed

- `src/sense_pulse/web/routes.py` - WebSocket endpoint, removed legacy endpoints
- `src/sense_pulse/web/templates/base.html` - Removed HTMX script
- `src/sense_pulse/web/templates/index.html` - Pure WebSocket JavaScript
- `src/sense_pulse/web/templates/partials/status_cards.html` - Added element IDs
- `README.md` - Updated documentation for WebSocket architecture

### Performance Improvements

**Before (HTMX Polling):**
- HTTP GET request every 5 seconds
- Server renders HTML partial
- DOM replacement overhead
- Network latency per request

**After (WebSocket Streaming):**
- Single persistent WebSocket connection
- JSON data every 500ms
- Direct DOM element updates
- Zero HTTP overhead after connection

### Migration from v0.7.0

No configuration changes required! Simply restart the service:

```bash
sudo systemctl restart sense-pulse
```

The dashboard will automatically connect to the new `/ws/dashboard` endpoint.

### Benefits

1. **10x Faster Updates**: 500ms vs 5s refresh rate
2. **Zero Polling Overhead**: Single WebSocket connection
3. **Simpler Stack**: No HTMX dependency
4. **Better UX**: Smooth real-time feel with instant updates
5. **Lower Bandwidth**: JSON vs HTML reduces data transfer
6. **Unified Architecture**: One WebSocket for all dashboard data

---

## Version 0.7.0 - Data Caching with Background Polling

### New Features

**Centralized Data Cache**
- All sensor and service data is now cached with a 60-second TTL (Time-To-Live)
- Background polling thread refreshes data every 30 seconds
- Web API and LED display read from cache instead of directly calling services
- Eliminates blocking API requests and improves responsiveness
- Thread-safe cache access for concurrent operations

**Performance Improvements**
- Web API endpoints respond instantly from cached data
- LED display updates use cached data, reducing sensor polling overhead
- Background thread ensures fresh data is always available
- Reduces redundant API calls to Pi-hole, Tailscale, and sensors

**Graceful Degradation**
- Cache returns empty data when sources are unavailable
- Background polling continues even if individual sources fail
- System remains responsive during temporary network issues

### Technical Changes

**New Module:**
- `src/sense_pulse/cache.py` - Centralized caching system with background polling
  - `DataCache` class with thread-safe operations
  - `get_cache()` - Get global cache instance
  - `initialize_cache()` - Initialize cache with custom TTL and poll interval

**Cache Architecture:**
- `CachedData` dataclass tracks data and timestamp
- `_polling_loop()` continuously polls all registered data sources
- Registered sources: Tailscale, Pi-hole, System Stats, Sense HAT, Aranet4 CO2

**CLI Updates:**
- `cli.py` initializes cache on startup with 60s TTL and 30s poll interval
- Starts background polling thread automatically

**Controller Updates:**
- `controller.py` reads from cache instead of direct service calls
- Registers data sources during initialization
- Display methods updated to use `cache.get()`

**Web Routes Updates:**
- `routes.py` endpoints serve cached data
- All API endpoints (`/api/status`, `/api/sensors`, etc.) read from cache
- Significantly reduced latency for API requests

### Files Changed

- `src/sense_pulse/cache.py` - New caching module
- `src/sense_pulse/cli.py` - Cache initialization and startup
- `src/sense_pulse/controller.py` - Display uses cached data
- `src/sense_pulse/web/routes.py` - API endpoints use cached data

### Migration from v0.6.0

No breaking changes! The caching system is transparent to users.

```bash
# Simply restart the service
sudo systemctl restart sense-pulse
```

The background polling will start automatically, and all data will be cached with the new system.

### Cache Status

To monitor cache status, check the logs:
```bash
sudo journalctl -u sense-pulse -f | grep -i cache
```

You'll see:
- Cache initialization messages
- Background polling activity
- Cache hit/miss statistics (in debug mode)

### Benefits

1. **Better Responsiveness**: Web API responds instantly from cache
2. **Reduced Load**: Services polled once every 30s instead of on every request
3. **Consistent Updates**: Display and web show data from the same polling cycle
4. **Improved Reliability**: Cached data available even during temporary failures

---

## Version 0.6.0 - Real-Time LED Matrix Preview

### New Features

**Single Process Architecture**
- Web server and LED display now run together in a single process by default
- Eliminates need for separate `sense-pulse-web.service`
- Shared in-memory state for real-time LED matrix preview
- New CLI options: `--web-only` (web server only) and `--no-web` (LED display only)

**Real-Time LED Matrix Preview**
- Live WebSocket feed reads directly from Sense HAT hardware via `get_pixels()`
- ~20 FPS update rate for smooth scrolling text visualization
- Web preview now shows exactly what's on the physical display in real-time
- Configurable `web_rotation_offset` to align web preview with physical display
- WebSocket connection persists across HTMX partial updates

**Fixed Config Toggles**
- Toggle buttons (Show Icons, Disable Pi LEDs, Rotation) now work correctly
- Endpoints return HTML partials instead of JSON for proper HTMX updates
- Changes apply immediately without page refresh

### Technical Changes

**CLI Updates:**
- Default: runs both LED display and web server
- `--web-only`: web server only (replaces `--web`)
- `--no-web`: LED display only
- `--web`: kept as hidden alias for backwards compatibility

**Hardware Module:**
- `get_matrix_state()` now reads directly from `sense_hat.get_pixels()`
- Removed redundant `_current_matrix` state tracking
- Added `_current_rotation` tracking for web preview sync

**Display Module:**
- Uses shared `hardware` module for all matrix operations
- Removed duplicate Sense HAT initialization

**Routes:**
- Toggle endpoints return `HTMLResponse` with rendered partials
- WebSocket update interval reduced from 500ms to 50ms

### Files Changed

- `src/sense_pulse/cli.py` - Single process with threading
- `src/sense_pulse/hardware.py` - Direct hardware pixel reading
- `src/sense_pulse/display.py` - Uses shared hardware module
- `src/sense_pulse/web/routes.py` - HTML responses for toggles
- `src/sense_pulse/web/templates/index.html` - Config-based rotation
- Removed: `sense-pulse-web.service`

### Migration from v0.5.0

**Service Changes:**
```bash
# Stop and disable old web service
sudo systemctl stop sense-pulse-web
sudo systemctl disable sense-pulse-web
sudo rm /etc/systemd/system/sense-pulse-web.service

# Restart main service (now includes web server)
sudo systemctl daemon-reload
sudo systemctl restart sense-pulse
```

The main service now runs both the LED display and web server automatically.

---

## Version 0.5.0 - Pi Onboard LED Control

### New Features

**Sleep Mode Pi LED Control**
- New `disable_pi_leds` option in sleep configuration
- Automatically turns off Pi's onboard LEDs (PWR red and ACT green) during sleep hours
- LEDs are restored when exiting sleep mode or on application shutdown
- Graceful degradation on non-Pi hardware (feature is silently skipped)

### Configuration

```yaml
sleep:
  start_hour: 22
  end_hour: 7
  disable_pi_leds: true  # NEW: Disable Pi onboard LEDs during sleep
```

### Technical Details

**New Module:**
- `src/sense_pulse/pi_leds.py` - Controls Pi onboard LEDs via `/sys/class/leds/`

**Functions:**
- `disable_led(name)` / `enable_led(name)` - Control individual LEDs
- `disable_all_leds()` / `enable_all_leds()` - Control both LEDs
- `get_led_status()` - Get current LED state
- `is_pi_led_available()` - Check if LEDs are controllable

**LED Control Flow:**
1. Saves original LED trigger settings (e.g., `mmc0` for ACT, `default-on` for PWR)
2. Sets trigger to `none` for manual control
3. Sets brightness to `0` to turn off
4. Restores original trigger when re-enabling

### Requirements

- Requires write access to `/sys/class/leds/` (run as root or configure udev rules)
- Works on Raspberry Pi models with accessible LED sysfs interface

### Migration from v0.4.0

No breaking changes! The feature is disabled by default.

To enable:
```yaml
# In config.yaml
sleep:
  disable_pi_leds: true
```

---

## Version 0.4.0 - Web Status Dashboard

### New Features

**Web Dashboard**
- Real-time status page accessible at `http://<pi-ip>:8080`
- Built with FastAPI, HTMX, and Tailwind CSS
- Dark theme with responsive design
- Works on any device with a web browser

**Status Cards**
- Tailscale connection status and device count
- Pi-hole queries, blocked ads, and block rate
- Environment sensors (temperature, humidity, pressure)
- System stats with CPU/memory progress bars
- Auto-refresh every 5 seconds via HTMX polling

**LED Matrix Preview**
- Real-time 8x8 LED grid visualization via WebSocket
- Colored pixels with glow effects
- Display mode indicator
- Updates at 500ms intervals

**Configuration Hot-Reload**
- Toggle show_icons from the web UI
- Change display rotation from dropdown
- Changes persist to config.yaml immediately
- No service restart required

**Hardware Abstraction**
- New `hardware.py` module for Sense HAT abstraction
- Graceful degradation when Sense HAT unavailable
- Dashboard works on any machine for development
- Clear "Hardware Unavailable" messages in UI

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web dashboard |
| `/health` | GET | Health check (always returns 200) |
| `/api/status` | GET | All status data as JSON |
| `/api/sensors` | GET | Sensor readings |
| `/api/matrix` | GET | Current LED matrix state |
| `/api/config` | GET | Current configuration |
| `/api/config` | POST | Update configuration |
| `/api/display/clear` | POST | Clear LED matrix |
| `/ws/matrix` | WebSocket | Real-time matrix updates |

### CLI Changes

New command-line options:
```
--web              Start web status server
--web-port PORT    Port for web server (default: 8080)
--web-host HOST    Host for web server (default: 0.0.0.0)
```

### New Dependencies

- `fastapi>=0.109.0` - Modern async web framework
- `uvicorn[standard]>=0.27.0` - ASGI server
- `jinja2>=3.1.0` - Template engine

### New Files

- `src/sense_pulse/hardware.py` - Hardware abstraction layer
- `src/sense_pulse/web/` - Web module
  - `app.py` - FastAPI application factory
  - `routes.py` - API endpoints
  - `templates/` - Jinja2 HTML templates
- `sense-pulse-web.service` - Systemd service for web dashboard

### Migration from v0.3.0

No breaking changes! The web dashboard is an additional feature.

To use the web dashboard:
```bash
# Run web server
uv run sense-pulse --web

# Or install as a service
sudo cp sense-pulse-web.service /etc/systemd/system/
sudo systemctl enable sense-pulse-web.service
sudo systemctl start sense-pulse-web.service
```

---

## Version 0.3.0 - Icon Display System

### New Features

**8x8 Pixel Art Icons**
- Added visual icons for all displayed stats
- Icons show for 1.5 seconds before text scrolls
- Configurable - can be toggled off for text-only mode
- 14 unique icons covering all display categories

**Icon Library:**
- Network icons (Tailscale connected/disconnected, devices)
- Pi-hole icons (shield, block, query)
- Sensor icons (thermometer, water drop, pressure gauge)
- Status icons (checkmark, X mark, arrows, heart)
- Loading spinner animation (4 frames)

**Configuration:**
- New `SHOW_ICONS` setting in config.py (default: True)
- Set to False for text-only display mode

### Icon Details

All icons are 8x8 pixel art designed for the Sense HAT LED matrix:
- **Tailscale Connected**: Green network link icon
- **Tailscale Disconnected**: Red broken link icon
- **Devices**: Cyan computer/network icon
- **Pi-hole Shield**: Green protection shield
- **Block**: Red stop/block icon
- **Query**: Green magnifying glass
- **Thermometer**: Orange/red temperature indicator
- **Water Drop**: Blue humidity indicator
- **Pressure Gauge**: Gray barometer with white needle

See `ICONS.md` for visual ASCII representations of all icons.

### Technical Implementation

**New Module:**
- `src/pihole_sense_display/icons.py` - Icon definitions and utilities
- `get_icon(name)` function for retrieving icons by name
- Color constants for consistency

**Display Enhancements:**
- `show_icon()` method - Display an 8x8 icon
- `show_icon_with_text()` method - Show icon then scroll text
- Updated all display methods to support icon mode

### Migration from v0.2.0

No breaking changes! Icons are enabled by default.

To upgrade:
```bash
cd ~/pihole-sense-display
# Copy new files or git pull
sudo systemctl restart pihole-sense-display.service
```

To disable icons (use text-only):
```python
# In config.py
SHOW_ICONS = False
```

---

## Version 0.2.0 - Tailscale Device Count

### New Features

**Tailscale Connected Device Count**
- Display now shows count of online devices in your Tailnet
- Appears as "TS Devices: X" in cyan color
- Only shown when Tailscale is connected
- Counts actively online peers (excludes offline devices and your own device)

### Technical Changes

**TailscaleStatus Class Enhancements:**
- Added `get_connected_device_count()` method
- Added `get_status_summary()` method for comprehensive status
- Implemented 30-second caching to reduce subprocess calls
- Improved JSON parsing of `tailscale status --json` output
- Better error handling for JSON parsing failures

**Display Updates:**
- `display_tailscale_status()` now shows both connection status and device count
- Device count only displays when connected (no clutter when disconnected)

### What Gets Counted

**Counted as "Connected Device":**
- Any peer in your Tailnet with `Online: true` status
- Devices that have recently communicated with the network
- Active connections (laptops, phones, servers, etc.)

**Not Counted:**
- Your own device (the Pi running this script)
- Offline devices in your Tailnet
- Devices that haven't checked in recently
- Disconnected peers

### Example Output on Display

When connected with 3 other devices online:
```
TS: Connected        (green)
TS Devices: 3        (cyan)
Queries: 1234        (green)
...
```

When disconnected:
```
TS: Disconnected     (red)
Queries: 1234        (green)
...
```

### Performance Notes

- Tailscale status is cached for 30 seconds
- Minimal performance impact (one JSON parse per 30s)
- No additional network calls (local subprocess only)

### Troubleshooting

If device count shows 0 but you expect devices:
1. Verify other devices are actually online: `tailscale status`
2. Check if Tailscale is running: `sudo systemctl status tailscaled`
3. Ensure devices aren't in "offline" state
4. Enable DEBUG logging to see detailed peer information

### Debugging Tips

Following your bottom-up approach, validate assumptions:

1. **Check raw Tailscale output:**
   ```bash
   tailscale status --json | python3 -m json.tool
   ```

2. **Verify peer count manually:**
   ```bash
   tailscale status --json | python3 -c "import sys, json; data=json.load(sys.stdin); print(f'Peers: {len(data.get(\"Peer\", {}))}')"
   ```

3. **Count online peers:**
   ```bash
   tailscale status --json | python3 -c "import sys, json; data=json.load(sys.stdin); online=[p for p in data.get('Peer',{}).values() if p.get('Online')]; print(f'Online: {len(online)}')"
   ```

4. **Check logs for details:**
   ```bash
   grep "Tailscale" /var/log/pihole_sense_display.log
   ```

### Configuration

No configuration changes required! The feature is automatically enabled.

Optional: Adjust cache duration in `src/pihole_sense_display/main.py`:
```python
self._cache_duration = 30  # Change to desired seconds
```

### Migration from v0.1.0

No breaking changes! Simply pull the latest code and restart the service:
```bash
cd ~/pihole-sense-display
git pull  # or copy new files
sudo systemctl restart pihole-sense-display.service
```
