# Sense Pulse

A Python application that displays Pi-hole statistics, Tailscale connection status, and Sense HAT sensor data on your Raspberry Pi's LED matrix.

## Features

- **Data Caching**: 60-second cache with 30-second background polling for instant API responses
- **Web Dashboard**: Real-time WebSocket-powered dashboard at port 8080 with 500ms updates
- **Visual Icons**: 8x8 pixel art icons for each stat (can be toggled off for text-only)
- **Tailscale Status**: Shows connection status and count of online devices in your Tailnet
- **Pi-hole Stats**: Queries today, ads blocked, block percentage
- **Sensor Data**: Temperature, humidity, atmospheric pressure
- **Aranet4 Monitoring**: Temperature, CO2, and humidity from Aranet4 sensors with color-coded alerts
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
6. **Sense HAT Temperature** (Orange)
7. **Sense HAT Humidity** (Blue)
8. **Sense HAT Pressure** (Gray)
9. **Aranet4 Temperature** (Orange - per sensor)
10. **Aranet4 CO2** (Color-coded: Green <1000ppm, Yellow <1500ppm, Red ≥1500ppm)
11. **Aranet4 Humidity** (Blue - per sensor)
12. **CPU Usage** (Yellow)
13. **Memory Usage** (Cyan)
14. **System Load** (Magenta)

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
        ├── context.py      # AppContext for dependency injection
        ├── cache.py        # Data caching with background polling
        ├── hardware.py     # Sense HAT abstraction layer
        ├── icons.py        # 8x8 LED pixel art
        ├── tailscale.py    # Tailscale status (legacy)
        ├── pihole.py       # Pi-hole stats (legacy)
        ├── system.py       # System stats (legacy)
        ├── display.py      # Sense HAT display
        ├── schedule.py     # Sleep schedule
        ├── controller.py   # Main controller
        ├── pi_leds.py      # Pi onboard LED control
        ├── aranet4.py      # Aranet4 CO2 sensor integration (legacy)
        ├── datasources/    # DataSource implementations
        │   ├── __init__.py
        │   ├── base.py     # DataSource interface
        │   ├── registry.py # Source management
        │   ├── pihole_source.py    # Pi-hole wrapper
        │   ├── tailscale_source.py # Tailscale wrapper
        │   ├── system_source.py    # System metrics wrapper
        │   ├── sensehat_source.py  # Sense HAT wrapper
        │   └── aranet4_source.py   # Aranet4 wrapper
        └── web/            # Web dashboard module
            ├── __init__.py
            ├── app.py      # FastAPI application
            ├── routes.py   # API endpoints
            ├── auth.py     # HTTP Basic Auth
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

## Development

### Architecture Overview

Sense Pulse uses a **dependency injection** architecture for clean, testable code:

**AppContext Pattern:**
- `AppContext` is the central dependency container
- Manages lifecycle of all data sources (Pi-hole, Tailscale, sensors, etc.)
- Injected into web app and display controller
- Eliminates global singletons and hidden dependencies

**Key Components:**
- `context.py` - AppContext for dependency injection
- `datasources/` - Unified DataSource interface implementations
- `cache.py` - Centralized data caching with background polling
- `controller.py` - Display controller (receives cache via injection)
- `web/app.py` - FastAPI app (receives context via injection)

**Data Flow:**
1. CLI creates `AppContext` from configuration
2. Context initializes all data sources
3. Context starts background cache polling
4. Context injected into web app and controller
5. Components read from shared cache
6. Unified shutdown cleans up all resources

**Benefits:**
- Explicit dependencies via constructor injection
- Easy to test with mock objects
- Single initialization point
- Clear lifecycle management
- No global state

### Setting Up Development Environment

```bash
# Clone repository
git clone https://github.com/yourusername/sense-pulse.git
cd sense-pulse

# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies (including dev dependencies)
uv sync --all-extras --dev

# Install pre-commit hooks
uv run pre-commit install
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=sense_pulse --cov-report=html

# Run specific test file
uv run pytest tests/test_cache.py

# Run with verbose output
uv run pytest -v
```

### Code Quality Tools

```bash
# Run linter (ruff)
uv run ruff check src/ tests/

# Auto-fix linting issues
uv run ruff check --fix src/ tests/

# Format code with black
uv run black src/ tests/

# Check formatting without changes
uv run black --check src/ tests/

# Type checking with mypy
uv run mypy src/

# Run all checks (pre-commit)
uv run pre-commit run --all-files
```

### Authentication Setup

To enable web dashboard authentication:

1. Generate a password hash:
```bash
uv run python -c "from sense_pulse.web.auth import get_password_hash; print(get_password_hash('your_secure_password'))"
```

2. Add to `config.yaml`:
```yaml
auth:
  enabled: true
  username: "admin"
  password_hash: "$2b$12$..."  # paste hash from step 1
```

3. Restart the service:
```bash
sudo systemctl restart sense-pulse
```

### Project Structure

```
sense-pulse/
├── .github/
│   └── workflows/
│       └── ci.yml              # GitHub Actions CI/CD
├── src/
│   └── sense_pulse/
│       ├── __init__.py
│       ├── cli.py              # CLI interface
│       ├── config.py           # Configuration management
│       ├── context.py          # AppContext for dependency injection
│       ├── cache.py            # Data caching with background polling
│       ├── controller.py       # Main display controller
│       ├── hardware.py         # Hardware abstraction
│       ├── pihole.py           # Pi-hole stats (legacy)
│       ├── tailscale.py        # Tailscale status (legacy)
│       ├── aranet4.py          # Aranet4 sensor integration (legacy)
│       ├── system.py           # System stats (legacy)
│       ├── display.py          # LED matrix display
│       ├── icons.py            # 8x8 pixel art icons
│       ├── schedule.py         # Sleep scheduling
│       ├── pi_leds.py          # Pi onboard LED control
│       ├── datasources/        # DataSource implementations
│       │   ├── __init__.py
│       │   ├── base.py         # DataSource interface
│       │   ├── registry.py     # Source management
│       │   ├── pihole_source.py    # Pi-hole wrapper
│       │   ├── tailscale_source.py # Tailscale wrapper
│       │   ├── system_source.py    # System metrics wrapper
│       │   ├── sensehat_source.py  # Sense HAT wrapper
│       │   └── aranet4_source.py   # Aranet4 wrapper
│       └── web/
│           ├── app.py          # FastAPI application
│           ├── routes.py       # API routes
│           ├── auth.py         # HTTP Basic Auth
│           └── templates/      # Jinja2 templates
├── tests/
│   ├── test_cache.py           # Cache module tests
│   ├── test_config.py          # Config module tests
│   ├── test_context.py         # AppContext tests
│   ├── test_cli_context.py     # CLI integration tests
│   ├── test_web_app.py         # Web app dependency injection tests
│   ├── test_datasources.py     # DataSource tests
│   └── test_auth.py            # Authentication tests
├── pyproject.toml              # Project config + tool settings
├── .pre-commit-config.yaml     # Pre-commit hooks
└── config.example.yaml         # Example configuration
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting (`uv run pytest && uv run ruff check src/`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Continuous Integration

The project uses GitHub Actions for CI:

- **Linting & Type Checking**: Runs ruff, black, and mypy
- **Tests**: Runs pytest on Python 3.9-3.12
- **Coverage**: Uploads coverage reports to Codecov
- **Security**: Runs bandit security scanner

## Security

### Reporting Security Issues

Please report security vulnerabilities privately to the maintainers.

### Security Features

- HTTP Basic Auth for web dashboard (bcrypt password hashing)
- No credentials stored in plain text
- All network calls use retry logic to prevent hanging
- Input validation on all API endpoints

## License

MIT License
