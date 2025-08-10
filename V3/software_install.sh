#!/bin/bash
# ProScout Software Installation Script
# Run AFTER sara-r5-installation.sh
# This script downloads ProScout software and adds it to existing sara_r5_startup.sh

INSTALL_DIR="/home/proscout/ProScout-master"
DEVICE_DIR="$INSTALL_DIR/device-manager"
VENV_DIR="$INSTALL_DIR/ProScout-Device"
LOGFILE="/var/log/proscout-install.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_message() {
    echo -e "${BLUE}$(date '+%Y-%m-%d %H:%M:%S')${NC} - $1" | sudo tee -a "$LOGFILE" > /dev/null
    echo -e "${BLUE}$(date '+%Y-%m-%d %H:%M:%S')${NC} - $1"
}

error_exit() {
    echo -e "${RED}ERROR: $1${NC}" | sudo tee -a "$LOGFILE" > /dev/null
    echo -e "${RED}ERROR: $1${NC}"
    exit 1
}

success_message() {
    echo -e "${GREEN}SUCCESS: $1${NC}" | sudo tee -a "$LOGFILE" > /dev/null
    echo -e "${GREEN}SUCCESS: $1${NC}"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    error_exit "This script should not be run as root. Run as regular user with sudo privileges."
fi

# Check if sara_r5_startup.sh exists (should be created by sara-r5-installation.sh)
if [ ! -f "/home/proscout/sara_r5_startup.sh" ]; then
    error_exit "sara_r5_startup.sh not found. Please run sara-r5-installation.sh first."
fi

# Create log file
sudo touch "$LOGFILE"
sudo chmod 666 "$LOGFILE"

log_message "=== Starting ProScout Software Installation ==="

# Update system and install Python packages
log_message "Installing required system packages..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git || error_exit "Failed to install system packages"

# Download ProScout software and create virtual environment
log_message "Downloading ProScout software and setting up virtual environment..."

sudo -u proscout bash << 'EOF'
INSTALL_DIR="/home/proscout/ProScout-master"
DEVICE_DIR="$INSTALL_DIR/device-manager"
VENV_DIR="$INSTALL_DIR/ProScout-Device"

cd /home/proscout

echo "Downloading ProScout software from GitHub..."
if [ -d "$DEVICE_DIR" ]; then
    rm -rf "$DEVICE_DIR"
fi

# Clone the repository
git clone --depth 1 --filter=blob:none --sparse https://github.com/proscoutAi/Device-Management.git temp-repo
cd temp-repo
git sparse-checkout set V2
cd ..

# Move to target location
mkdir -p "$INSTALL_DIR"
mv temp-repo/V2 "$DEVICE_DIR"
rm -rf temp-repo

if [ ! -d "$DEVICE_DIR" ]; then
    echo "ERROR: Failed to download software"
    exit 1
fi

echo "Software downloaded successfully"

# Create virtual environment
echo "Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"

if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "ERROR: Failed to create virtual environment"
    exit 1
fi

# Install dependencies
echo "Installing dependencies..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip

if [ -f "$DEVICE_DIR/requirements.txt" ]; then
    pip install -r "$DEVICE_DIR/requirements.txt"
else
    pip install requests pyserial gps3 pynmea2 psutil opencv-python-headless numpy RPi.GPIO gpiozero smbus smbus2
fi

echo "Dependencies installed successfully"
EOF

# Check if ProScout startup is already added to sara_r5_startup.sh
if grep -q "ProScout application" /home/proscout/sara_r5_startup.sh; then
    log_message "ProScout startup already exists in sara_r5_startup.sh"
else
    log_message "Adding ProScout startup to sara_r5_startup.sh..."
    
    # Add ProScout startup to the end of the existing script
    sudo -u proscout tee -a /home/proscout/sara_r5_startup.sh > /dev/null << 'EOF'

# Wait a bit for everything to stabilize
sleep 10

# Start ProScout Application
echo "$(date): Starting ProScout application..."
cd /home/proscout/ProScout-master/device-manager/
source /home/proscout/ProScout-master/ProScout-Device/bin/activate
nohup python3 main.py >> /var/log/proscout.log 2>&1 &
PROSCOUT_PID=$!
echo "$(date): ProScout application started with PID: $PROSCOUT_PID"
EOF
    
    success_message "ProScout startup added to sara_r5_startup.sh"
fi

# Set up ProScout log file
sudo touch /var/log/proscout.log
sudo chown proscout:proscout /var/log/proscout.log
sudo chmod 644 /var/log/proscout.log

success_message "ProScout software installation completed!"

log_message "=== Installation Summary ==="
log_message "Software installed in: $DEVICE_DIR"
log_message "Virtual environment: $VENV_DIR"
log_message "Added to startup script: /home/proscout/sara_r5_startup.sh"
log_message "ProScout log: /var/log/proscout.log"

echo
echo -e "${GREEN}=== Installation Complete! ===${NC}"
echo "ProScout has been added to your existing sara_r5_startup.sh script."
echo "The script will now start SARA-R5 services followed by ProScout application."
echo

read -p "Would you like to reboot now to test the complete setup? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_message "Rebooting system..."
    sudo reboot
else
    echo "Please reboot manually to test the complete setup: sudo reboot"
fi