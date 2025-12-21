#!/bin/bash

# Script to install and enable the LED service
# This script must be run with sudo privileges

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="leds-service.service"
SERVICE_NAME="leds-service"
SYSTEMD_DIR="/etc/systemd/system"

echo "=== Installing LED Service ==="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Error: This script must be run as root (use sudo)"
    exit 1
fi

# Check if service file exists
if [ ! -f "$SCRIPT_DIR/$SERVICE_FILE" ]; then
    echo "Error: Service file $SERVICE_FILE not found in $SCRIPT_DIR"
    exit 1
fi

# Copy service file to systemd directory
echo "Copying service file to $SYSTEMD_DIR..."
cp "$SCRIPT_DIR/$SERVICE_FILE" "$SYSTEMD_DIR/$SERVICE_FILE"

# Reload systemd daemon
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Unmask service if it's masked (prevents starting)
if systemctl is-enabled "$SERVICE_NAME" 2>/dev/null | grep -q "masked"; then
    echo "Service is masked. Unmasking..."
    systemctl unmask "$SERVICE_NAME"
fi

# Enable service to start on boot
echo "Enabling service to start on boot..."
systemctl enable "$SERVICE_NAME"

# Start the service
echo "Starting service..."
systemctl start "$SERVICE_NAME"

# Check service status
echo ""
echo "=== Service Status ==="
systemctl status "$SERVICE_NAME" --no-pager -l

echo ""
echo "=== Installation Complete ==="
echo "Service '$SERVICE_NAME' has been installed and started."
echo ""
echo "Useful commands:"
echo "  Check status:    sudo systemctl status $SERVICE_NAME"
echo "  Stop service:    sudo systemctl stop $SERVICE_NAME"
echo "  Start service:   sudo systemctl start $SERVICE_NAME"
echo "  Restart service: sudo systemctl restart $SERVICE_NAME"
echo "  View logs:       sudo journalctl -u $SERVICE_NAME -f"
echo "  Disable service: sudo systemctl disable $SERVICE_NAME"
