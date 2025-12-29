# Sense Pulse

A Python application that displays Pi-hole statistics, Tailscale connection status, and Sense HAT sensor data on your Raspberry Pi's LED matrix.

## Features

- **Data Caching**: 60-second cache with 30-second background polling for instant API responses
- **Web Dashboard**: Real-time WebSocket-powered dashboard at port 8080 with 500ms updates
- **Visual Icons**: 8x8 pixel art icons for each stat (can be toggled off for text-only)
- **Tailscale Status**: Shows connection status and count of online devices in your Tailnet
- **Pi-hole Stats**: Queries today, ads blocked, block percentage
- **Sensor Data**: Temperature, humidity, atmospheric pressure
- **CO2 Monitoring**: Aranet4 CO2 sensor integration with color-coded alerts
- **System Stats**: CPU usage, memory usage, system load average
- **Sleep Hours**: Automatically turns off display during configured hours
- **Pi LED Control**: Optionally disable Pi's onboard LEDs (PWR/ACT) during sleep
- **YAML Configuration**: Easy-to-edit config file with hot-reload
- **Auto-start**: Runs as a systemd daemon

## Display Cycle

The LED matrix cycles through:

1. **Tailscale Connection Status** (Green=Connected, Red=Disconnected)
2. **Tailscale Connected Devices** (Cyan - only shown if connected)
3. **DNS Queries Today** (Green)
4. **Ads Blocked Today** (Red)
5. **Block Percentage** (Orange)
6. **Temperature** (Orange)
7. **Humidity** (Blue)
8. **Pressure** (Gray)
9. **CPU Usage** (Yellow)
10. **Memory Usage** (Cyan)
11. **System Load** (Magenta)

## Web Dashboard

Sense Pulse includes a web-based status dashboard accessible from any browser. The web server runs automatically alongside the LED display in a single process.

### Features

- **Real-time WebSocket Updates**: All sensor data streams via WebSocket at 500ms intervals
- **Live LED Matrix Preview**: Real-time 8x8 LED display preview with smooth animations
- **Configuration Controls**: Toggle icons, change rotation from the browser
- **Graceful Degradation**: Works without Sense HAT hardware (sensor data shows as unavailable)
- **Dark Theme**: Beautiful dark UI with Tailwind CSS
- **Zero Polling Overhead**: Single WebSocket connection for all dashboard data

### Quick Start

```bash
# Start display + web server (default)
uv run sense-pulse

# Web server only (no LED display)
uv run sense-pulse --web-only

# LED display only (no web server)
uv run sense-pulse --no-web

# Custom port
uv run sense-pulse --web-port 3000

# With verbose logging
uv run sense-pulse --verbose
```

Then open `http://<your-pi-ip>:8080` in your browser.

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web dashboard |
| `/health` | GET | Health check |
| `/api/status` | GET | All status data as JSON |
| `/api/sensors` | GET | Sensor readings |
| `/api/config` | GET | Current configuration |
| `/api/config` | POST | Update configuration |
| `/ws/dashboard` | WebSocket | Real-time dashboard updates (all sensor data + LED matrix) |

### Running as a Service

The web dashboard runs automatically with the main service - no separate service needed:

```bash
sudo cp sense-pulse.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sense-pulse.service
sudo systemctl start sense-pulse.service
```

The web dashboard will be available at `http://<your-pi-ip>:8080`.

## Prerequisites

- Raspberry Pi 3 B+ (or compatible)
- Sense HAT V1
- Pi-hole installed and running
- Tailscale installed and configured
- Python 3.9 or higher

## Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/sense-pulse.git
cd sense-pulse

# Run setup script
./setup.sh
```

## Manual Installation

### 1. Install uv (Python Package Manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

### 2. Install System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y python3-sense-hat i2c-tools
```

> **Note:** The `python3-sense-hat` package includes RTIMU which cannot be installed via pip. The project is configured to use system packages.

### 3. Enable I2C (if not already enabled)

```bash
sudo raspi-config
# Navigate to: Interface Options -> I2C -> Enable
# Reboot when prompted
```

### 4. Install Project Dependencies

```bash
cd ~/sense-pulse
uv sync
```

### 5. Configure

```bash
# Copy example config
cp config.example.yaml config.yaml

# Edit configuration
nano config.yaml
```

### 6. Test

```bash
# Run single cycle
uv run sense-pulse --once --verbose

# Run continuously
uv run sense-pulse
```

## Configuration

Edit `config.yaml` to customize:

```yaml
# Pi-hole v6 settings
pihole:
  host: "http://localhost"
  password: ""  # Get from Pi-hole Settings > API > App password

# Tailscale settings
tailscale:
  cache_duration: 30  # seconds to cache status

# Display settings
display:
  rotation: 0              # 0, 90, 180, or 270 degrees
  show_icons: true         # Show 8x8 pixel icons before text
  scroll_speed: 0.05       # Text scroll speed (lower = faster)
  icon_duration: 1.5       # How long to show icons (seconds)
  web_rotation_offset: 90  # Rotation offset for web preview (0, 90, 180, 270)

# Sleep schedule (display turns off during these hours)
sleep:
  start_hour: 22       # 10 PM
  end_hour: 7          # 7 AM
  disable_pi_leds: false  # Also turn off Pi's red/green onboard LEDs

# Update settings
update:
  interval: 60         # Seconds between display cycles

# Logging
logging:
  level: "INFO"        # DEBUG, INFO, WARNING, ERROR
  file: "/var/log/sense-pulse.log"

# Web dashboard settings
web:
  enabled: true        # Enable web dashboard
  host: "0.0.0.0"      # Bind address (0.0.0.0 for all interfaces)
  port: 8080           # Web server port
```

## Running as a Service

### 1. Create Log File

```bash
sudo touch /var/log/sense-pulse.log
sudo chmod 644 /var/log/sense-pulse.log
```

### 2. Install the Service

```bash
sudo cp sense-pulse.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### 3. Enable and Start

```bash
sudo systemctl enable sense-pulse.service
sudo systemctl start sense-pulse.service
sudo systemctl status sense-pulse.service
```

### 4. Managing the Service

```bash
# Stop
sudo systemctl stop sense-pulse.service

# Restart
sudo systemctl restart sense-pulse.service

# View logs
sudo journalctl -u sense-pulse -f
```

## Command Line Options

```
sense-pulse [OPTIONS]

Options:
  -V, --version         Show version
  -c, --config PATH     Path to config file
  --once                Run one display cycle and exit
  -v, --verbose         Enable debug logging
  --web-only            Start web server only (no LED display)
  --no-web              Disable web server (LED display only)
  --web-port PORT       Port for web server (default: 8080)
  --web-host HOST       Host for web server (default: 0.0.0.0)
  -h, --help            Show help
```

By default, both the LED display and web server run together in a single process.

## Project Structure

```
sense-pulse/
├── pyproject.toml          # Project configuration
├── config.example.yaml     # Example configuration
├── config.yaml             # Your configuration (gitignored)
├── sense-pulse.service     # Systemd service file (runs display + web)
├── 99-pi-leds.rules        # udev rules for LED control without root
├── setup.sh                # Setup script
├── README.md
└── src/
    └── sense_pulse/
        ├── __init__.py     # Package version
        ├── __main__.py     # python -m entry point
        ├── cli.py          # Command-line interface
        ├── config.py       # Configuration loading
        ├── cache.py        # Data caching with background polling
        ├── hardware.py     # Sense HAT abstraction layer
        ├── icons.py        # 8x8 LED pixel art
        ├── tailscale.py    # Tailscale status
        ├── pihole.py       # Pi-hole stats
        ├── system.py       # System stats (CPU, memory, load)
        ├── display.py      # Sense HAT display
        ├── schedule.py     # Sleep schedule
        ├── controller.py   # Main controller
        ├── pi_leds.py      # Pi onboard LED control
        ├── aranet4.py      # Aranet4 CO2 sensor integration
        └── web/            # Web dashboard module
            ├── __init__.py
            ├── app.py      # FastAPI application
            ├── routes.py   # API endpoints
            └── templates/  # Jinja2 HTML templates
```

## Troubleshooting

### Tailscale Command Not Found

```bash
# Verify Tailscale is installed
which tailscale

# If not found, install it
curl -fsSL https://tailscale.com/install.sh | sh
```

### Pi-hole API Not Accessible (v6)

```bash
# Test Pi-hole v6 API
curl http://localhost/api/stats/summary

# If you get 401, you need to set up authentication:
# 1. Go to Pi-hole Settings > API
# 2. Create an App password
# 3. Add it to config.yaml under pihole.password

# Check Pi-hole is running
sudo systemctl status pihole-FTL
```

### Sense HAT Not Detected

```bash
# Check I2C devices
sudo i2cdetect -y 1

# Test Sense HAT
python3 -c "from sense_hat import SenseHat; s = SenseHat(); print('OK')"
```

### Service Won't Start

```bash
# Check service status
sudo systemctl status sense-pulse.service

# View logs
sudo journalctl -u sense-pulse -n 50
```

### Pi Onboard LEDs Not Turning Off

The `disable_pi_leds` feature requires write access to `/sys/class/leds/`.

**Install udev rules (recommended):**
```bash
# Install the provided udev rules file
sudo cp 99-pi-leds.rules /etc/udev/rules.d/

# Reload udev rules
sudo udevadm control --reload-rules && sudo udevadm trigger

# Verify permissions (should now be world-writable)
ls -la /sys/class/leds/ACT/brightness
```

**Manual testing:**
```bash
# Test LED control (should work without sudo after udev rules)
echo none > /sys/class/leds/ACT/trigger
echo 0 > /sys/class/leds/ACT/brightness
echo mmc0 > /sys/class/leds/ACT/trigger  # restore
```

## License

MIT License
