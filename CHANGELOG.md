# Changelog

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
