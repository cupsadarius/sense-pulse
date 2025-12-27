# Changelog

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
