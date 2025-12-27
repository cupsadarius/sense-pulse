# Sense Pulse

A Python application that displays Pi-hole statistics, Tailscale connection status, and Sense HAT sensor data on your Raspberry Pi's LED matrix.

## Features

- **Visual Icons**: 8x8 pixel art icons for each stat (can be toggled off for text-only)
- **Tailscale Status**: Shows connection status and count of online devices in your Tailnet
- **Pi-hole Stats**: Queries today, ads blocked, block percentage
- **Sensor Data**: Temperature, humidity, atmospheric pressure
- **Sleep Hours**: Automatically turns off display during configured hours
- **YAML Configuration**: Easy-to-edit config file
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
# Pi-hole settings
pihole:
  api_url: "http://localhost/admin/api.php"

# Tailscale settings
tailscale:
  cache_duration: 30  # seconds to cache status

# Display settings
display:
  rotation: 0          # 0, 90, 180, or 270 degrees
  show_icons: true     # Show 8x8 pixel icons before text
  scroll_speed: 0.05   # Text scroll speed (lower = faster)
  icon_duration: 1.5   # How long to show icons (seconds)

# Sleep schedule (display turns off during these hours)
sleep:
  start_hour: 22       # 10 PM
  end_hour: 7          # 7 AM

# Update settings
update:
  interval: 60         # Seconds between display cycles

# Logging
logging:
  level: "INFO"        # DEBUG, INFO, WARNING, ERROR
  file: "/var/log/sense-pulse.log"
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
  -h, --help            Show help
```

## Project Structure

```
sense-pulse/
├── pyproject.toml          # Project configuration
├── config.example.yaml     # Example configuration
├── config.yaml             # Your configuration (gitignored)
├── sense-pulse.service     # Systemd service file
├── setup.sh                # Setup script
├── README.md
└── src/
    └── sense_pulse/
        ├── __init__.py     # Package version
        ├── __main__.py     # python -m entry point
        ├── cli.py          # Command-line interface
        ├── config.py       # Configuration loading
        ├── icons.py        # 8x8 LED pixel art
        ├── tailscale.py    # Tailscale status
        ├── pihole.py       # Pi-hole stats
        ├── display.py      # Sense HAT display
        ├── schedule.py     # Sleep schedule
        └── controller.py   # Main controller
```

## Troubleshooting

### Tailscale Command Not Found

```bash
# Verify Tailscale is installed
which tailscale

# If not found, install it
curl -fsSL https://tailscale.com/install.sh | sh
```

### Pi-hole API Not Accessible

```bash
# Test API
curl http://localhost/admin/api.php

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

## License

MIT License
