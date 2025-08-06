#!/bin/bash
# ProScout Complete Installation Script
# Run with: bash install-proscout.sh (NOT as root)

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

warning_message() {
    echo -e "${YELLOW}WARNING: $1${NC}" | sudo tee -a "$LOGFILE" > /dev/null
    echo -e "${YELLOW}WARNING: $1${NC}"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    error_exit "This script should not be run as root. Run as regular user with sudo privileges."
fi

# Create log file with proper permissions first
sudo touch "$LOGFILE"
sudo chmod 666 "$LOGFILE"

log_message "=== Starting ProScout Installation ==="

# Update system packages
log_message "Updating system packages..."
sudo apt update || error_exit "Failed to update package lists"

# ===============================================
# Fix DNS Resolution First (Critical for downloads)
# ===============================================
log_message "🌐 Configuring DNS resolution..."

# Set up reliable DNS servers
sudo tee /etc/resolv.conf > /dev/null << 'EOF'
nameserver 8.8.8.8
nameserver 1.1.1.1
nameserver 8.8.4.4
nameserver 1.0.0.1
EOF

# Configure NetworkManager to not overwrite DNS
sudo mkdir -p /etc/NetworkManager/conf.d
sudo tee /etc/NetworkManager/conf.d/dns.conf > /dev/null << EOF
[main]
dns=none
EOF

# Make resolv.conf immutable so nothing can overwrite it
sudo chattr +i /etc/resolv.conf 2>/dev/null || true

# Test DNS resolution
log_message "🧪 Testing DNS resolution..."
if ping -c 2 google.com &>/dev/null; then
    success_message "DNS resolution working"
else
    warning_message "DNS resolution may have issues - continuing anyway"
fi

# Restart NetworkManager to apply DNS changes
sudo systemctl restart NetworkManager 2>/dev/null || true

# Install required system packages
log_message "Installing required system packages..."
sudo apt install -y python3 python3-pip python3-venv git wget curl unzip python3-smbus python3-smbus2 i2c-tools python3-gpiozero python3-rpi.gpio || error_exit "Failed to install system packages"

# Enable I2C interface
log_message "Enabling I2C interface..."
sudo raspi-config nonint do_i2c 0

# Create proscout user if doesn't exist
if ! id "proscout" &>/dev/null; then
    log_message "Creating proscout user..."
    sudo useradd -m -s /bin/bash proscout
    sudo usermod -aG dialout,tty,i2c,gpio proscout
    success_message "Created proscout user"
else
    log_message "User proscout already exists"
    sudo usermod -aG dialout,tty,i2c,gpio proscout
fi

# Create directory structure
log_message "Creating directory structure..."
sudo mkdir -p "$INSTALL_DIR"
sudo chown -R proscout:proscout /home/proscout
success_message "Directory structure created"

# Switch to proscout user for remaining operations
log_message "Switching to proscout user context..."

# Download the software from GitHub
sudo -u proscout bash << 'EOF'
INSTALL_DIR="/home/proscout/ProScout-master"
DEVICE_DIR="$INSTALL_DIR/device-manager"
VENV_DIR="$INSTALL_DIR/ProScout-Device"
LOGFILE="/var/log/proscout-install.log"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOGFILE"
}

cd /home/proscout

log_message "Downloading ProScout software from GitHub..."
if [ -d "$DEVICE_DIR" ]; then
    log_message "Removing existing device-manager directory..."
    rm -rf "$DEVICE_DIR"
fi

# Clone the specific directory from the repository
git clone --depth 1 --filter=blob:none --sparse https://github.com/proscoutAi/Device-Management.git temp-repo
cd temp-repo
git sparse-checkout set V2
cd ..

# Move the V2 directory to our target location
mkdir -p "$INSTALL_DIR"
mv temp-repo/V2 "$DEVICE_DIR"
rm -rf temp-repo

if [ ! -d "$DEVICE_DIR" ]; then
    echo "ERROR: Failed to download software" | tee -a "$LOGFILE"
    exit 1
fi

log_message "Software downloaded successfully"

# Create Python virtual environment
log_message "Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"

if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "ERROR: Failed to create virtual environment" | tee -a "$LOGFILE"
    exit 1
fi

log_message "Virtual environment created successfully"

# Activate virtual environment and install dependencies
log_message "Activating virtual environment and installing dependencies..."
source "$VENV_DIR/bin/activate"

# Upgrade pip first
pip install --upgrade pip

# Check if requirements.txt exists and install dependencies
if [ -f "$DEVICE_DIR/requirements.txt" ]; then
    log_message "Installing dependencies from requirements.txt..."
    pip install -r "$DEVICE_DIR/requirements.txt"
    # Install additional common dependencies that might be missing
    log_message "Installing additional sensor and GPIO libraries..."
    pip install psutil opencv-python-headless numpy \
        RPi.GPIO gpiozero lgpio rgpio colorzero \
        smbus smbus2 \
        adafruit-blinka adafruit-circuitpython-busdevice adafruit-circuitpython-register \
        adafruit-circuitpython-bmp3xx adafruit-circuitpython-bmp280 adafruit-circuitpython-bme280 \
        adafruit-circuitpython-lis3dh adafruit-circuitpython-lsm6ds adafruit-circuitpython-ads1x15
else
    log_message "No requirements.txt found, installing comprehensive sensor library set..."
    pip install requests pyserial gps3 pynmea2 psutil opencv-python-headless numpy \
        RPi.GPIO gpiozero lgpio rgpio colorzero \
        smbus smbus2 \
        adafruit-blinka adafruit-circuitpython-busdevice adafruit-circuitpython-register \
        adafruit-circuitpython-bmp3xx adafruit-circuitpython-bmp280 adafruit-circuitpython-bme280 \
        adafruit-circuitpython-lis3dh adafruit-circuitpython-lsm6ds adafruit-circuitpython-ads1x15
fi

log_message "Dependencies installed successfully"

# Test critical imports
log_message "Testing critical library imports..."
source "$VENV_DIR/bin/activate"

# Test imports and log results
python3 -c "
import sys
libraries = [
    'psutil', 'cv2', 'numpy', 'RPi.GPIO', 'gpiozero', 'lgpio', 
    'smbus', 'smbus2', 'board', 'busio', 'adafruit_bmp3xx'
]

print('Testing library imports...')
failed = []
for lib in libraries:
    try:
        __import__(lib)
        print(f'✓ {lib}')
    except ImportError as e:
        print(f'✗ {lib}: {e}')
        failed.append(lib)

if failed:
    print(f'Failed imports: {failed}')
    sys.exit(1)
else:
    print('All critical libraries imported successfully!')
"

if [ $? -ne 0 ]; then
    log_message "WARNING: Some library imports failed. Application may have issues."
else
    log_message "SUCCESS: All critical libraries imported successfully"
fi
EOF

# Since you're using crontab, we need to add ProScout startup to the existing modem script
log_message "Adding ProScout startup to existing modem script..."

# Check if the modem script exists
if [ ! -f "/usr/local/bin/modem-complete-start.sh" ]; then
    error_exit "Modem script not found. Please run the modem installation script first."
fi

# Check if ProScout startup is already added
if grep -q "ProScout-Device/bin/activate" "/usr/local/bin/modem-complete-start.sh"; then
    log_message "ProScout startup already exists in modem script"
else
    log_message "Adding ProScout startup to modem script..."
    
    # Add the ProScout startup lines to the end of the modem script
    sudo tee -a /usr/local/bin/modem-complete-start.sh > /dev/null << 'EOF'

# Start ProScout Application
log_message "Starting ProScout application..."
cd /home/proscout/ProScout-master/device-manager/
source /home/proscout/ProScout-master/ProScout-Device/bin/activate
nohup python3 main.py >> /var/log/proscout.log 2>&1 &
PROSCOUT_PID=$!
log_message "ProScout application started with PID: $PROSCOUT_PID"

# Give it a moment to start and verify
sleep 3
if kill -0 $PROSCOUT_PID 2>/dev/null; then
    log_message "SUCCESS: ProScout application is running"
else
    log_message "ERROR: ProScout application failed to start"
fi
EOF

    success_message "ProScout startup added to modem script"
fi

# Since modem runs via crontab, we'll keep your existing approach
# Just update the modem script to properly hand off to the service
log_message "Your modem script already runs via crontab - keeping that approach"
log_message "The existing modem script will continue to run the Python application"

# Set up log files with proper permissions
log_message "Setting up log files..."
sudo touch /var/log/proscout.log
sudo chown proscout:proscout /var/log/proscout.log
sudo chmod 644 /var/log/proscout.log

# No systemd configuration needed since using crontab
log_message "Configuration complete - using crontab for boot startup"

success_message "ProScout installation completed successfully!"

log_message "=== Installation Summary ==="
log_message "Software installed in: $DEVICE_DIR"
log_message "Virtual environment: $VENV_DIR"
log_message "Log file: /var/log/proscout.log"

echo
echo -e "${GREEN}=== Next Steps ===${NC}"
echo "1. Reboot to test the complete setup:"
echo "   sudo reboot"
echo "2. Check that everything started correctly:"
echo "   tail -f /var/log/modem-start.log"
echo "   tail -f /var/log/proscout.log"
echo "3. Verify ProScout is running:"
echo "   ps aux | grep python3"
echo "4. Check your crontab (should show the modem script):"
echo "   crontab -l"
echo
echo -e "${BLUE}The complete flow: Boot → Crontab → Modem Init → ProScout Startup${NC}"