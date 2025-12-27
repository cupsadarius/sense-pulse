#!/bin/bash
# Quick setup script for Sense Pulse

set -e

echo "=================================="
echo "Sense Pulse Setup"
echo "=================================="
echo ""

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "Warning: This doesn't appear to be a Raspberry Pi"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Install system dependencies
echo "Step 1/6: Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3-sense-hat i2c-tools curl

# Install uv if not present
if ! command -v uv &> /dev/null; then
    echo "Step 2/6: Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "Step 2/6: uv already installed"
fi

# Sync dependencies with system site packages (for sense-hat/RTIMU)
echo "Step 3/6: Installing Python dependencies..."
rm -rf .venv
uv venv --system-site-packages
uv sync

# Create config file if it doesn't exist
echo "Step 4/6: Setting up configuration..."
if [ ! -f config.yaml ]; then
    cp config.example.yaml config.yaml
    echo "Created config.yaml from template"
    echo "Edit config.yaml to customize settings"
else
    echo "config.yaml already exists"
fi

# Create log file
echo "Step 5/6: Creating log file..."
sudo touch /var/log/sense-pulse.log
sudo chown root:root /var/log/sense-pulse.log
sudo chmod 644 /var/log/sense-pulse.log

# Test run
echo "Step 6/6: Testing application..."
echo "Running a single display cycle..."
echo ""
uv run sense-pulse --once --verbose || true

echo ""
echo "=================================="
echo "Setup complete!"
echo "=================================="
echo ""
echo "Next steps:"
echo "1. Edit configuration: nano config.yaml"
echo "2. Test manually: uv run sense-pulse --once"
echo "3. Install as service:"
echo "   sudo cp sense-pulse.service /etc/systemd/system/"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable sense-pulse.service"
echo "   sudo systemctl start sense-pulse.service"
echo ""
echo "Commands:"
echo "  uv run sense-pulse              # Run continuously"
echo "  uv run sense-pulse --once       # Single cycle"
echo "  uv run sense-pulse --verbose    # Debug mode"
echo "  uv run sense-pulse --help       # Show all options"
echo ""
echo "See README.md for full documentation"
