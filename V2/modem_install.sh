#!/bin/bash

# OZZMaker SARA-R5 LTE-M GPS Auto-Installer
# Follows the exact OZZMaker installation guides:
# 1. Enable multiplexing: https://ozzmaker.com/how-to-enable-multiplexing-on-the-raspberry-pi-serial-interface/
# 2. Enable modem PPP: https://ozzmaker.com/using-the-lte-m-cellular-modem-to-create-a-data-connection-with-ppp/
# 3. Enable GPS: https://ozzmaker.com/using-the-gps-on-ozzmaker-sara-r5-lte-m-gps-10dof/

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration variables - EDIT THESE FOR YOUR SETUP
APN="net.hotm"                        # Replace with your carrier's APN
PROVIDER_NAME="HOT Mobile"              # Name for your provider (used in PPP peer config)

# Logging functions
log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   error "This script should not be run as root. Run as regular user with sudo access."
fi

echo "=========================================="
echo "🚀 OZZMaker SARA-R5 LTE-M GPS Installer"
echo "=========================================="
echo "Following OZZMaker official guides:"
echo "1. Enable multiplexing"
echo "2. Enable modem PPP connection"  
echo "3. Enable GPS streaming"
echo "4. Configure I2C for sensors"
echo "5. Enable auto-login"
echo
echo "📋 Configuration:"
echo "   APN: $APN"
echo "   Provider: $PROVIDER_NAME"
echo

read -p "📝 Continue with installation? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Installation cancelled."
    exit 0
fi

# ===============================================
# STEP 1: Enable Multiplexing (OZZMaker Guide 1)
# ===============================================
echo
echo "=========================================="
log "📡 STEP 1: Enable Multiplexing"
echo "=========================================="

log "🔄 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# ===============================================
# STEP 1.1: Fix DNS Resolution (Critical for downloads)
# ===============================================
log "🌐 Configuring DNS resolution..."

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
log "🧪 Testing DNS resolution..."
if ping -c 2 google.com &>/dev/null; then
    log "✅ DNS resolution working"
else
    warn "DNS resolution may have issues - continuing anyway"
fi

# Restart NetworkManager to apply DNS changes
sudo systemctl restart NetworkManager 2>/dev/null || true

log "📦 Installing required packages..."
sudo apt install -y ppp minicom gpsd gpsd-clients i2c-tools python3-smbus python3-smbus2 git

# ===============================================
# STEP 1.5: Enable I2C Interface (Added for sensors)
# ===============================================
echo
log "🔌 Enabling I2C interface for sensor communication..."

# Enable I2C via raspi-config
log "🔧 Enabling I2C interface..."
sudo raspi-config nonint do_i2c 0

# Get config file path
if [ -f /boot/firmware/config.txt ]; then
    CONFIG_FILE="/boot/firmware/config.txt"
elif [ -f /boot/config.txt ]; then
    CONFIG_FILE="/boot/config.txt"
else
    error "Could not find config.txt"
fi

# Verify I2C is enabled in config.txt
if ! grep -q "dtparam=i2c_arm=on" "$CONFIG_FILE"; then
    log "🔧 Adding I2C to config.txt..."
    echo "dtparam=i2c_arm=on" | sudo tee -a "$CONFIG_FILE"
fi

# Load I2C modules
log "🔧 Loading I2C kernel modules..."
sudo modprobe i2c-dev 2>/dev/null || true
sudo modprobe i2c-bcm2835 2>/dev/null || true

# Add modules to load at boot
if ! grep -q "i2c-dev" /etc/modules; then
    echo "i2c-dev" | sudo tee -a /etc/modules
fi
if ! grep -q "i2c-bcm2835" /etc/modules; then
    echo "i2c-bcm2835" | sudo tee -a /etc/modules
fi

log "🔌 I2C configuration completed"

# ===============================================
# STEP 1.6: Configure Auto-login
# ===============================================
echo
log "🔐 Configuring auto-login..."

# Enable console auto-login using raspi-config
log "🔧 Enabling console auto-login..."
sudo raspi-config nonint do_boot_behaviour B2

# Verify the setting
BOOT_CLI=$(sudo raspi-config nonint get_boot_cli)
AUTOLOGIN=$(sudo raspi-config nonint get_autologin)

if [ "$BOOT_CLI" = "0" ] && [ "$AUTOLOGIN" = "0" ]; then
    log "✅ Auto-login to desktop enabled"
elif [ "$BOOT_CLI" = "1" ] && [ "$AUTOLOGIN" = "0" ]; then
    log "✅ Auto-login to console enabled"
else
    warn "Auto-login configuration may not be set correctly"
    log "🔧 Manually setting console auto-login..."
    
    # Fallback method - directly configure systemd
    sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
    sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf > /dev/null << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $USER --noclear %I \$TERM
EOF
    
    # Reload systemd
    sudo systemctl daemon-reload
    log "✅ Manual auto-login configuration applied"
fi

log "🔐 Auto-login configuration completed"

log "🔧 Disabling serial console via raspi-config..."
# Disable serial console but enable serial port
sudo raspi-config nonint do_serial 1  # Disable serial console
sudo systemctl disable serial-getty@ttyS0.service 2>/dev/null || true
sudo systemctl disable serial-getty@ttyAMA0.service 2>/dev/null || true

# Remove console from cmdline.txt
if [ -f /boot/firmware/cmdline.txt ]; then
    CMDLINE_FILE="/boot/firmware/cmdline.txt"
elif [ -f /boot/cmdline.txt ]; then
    CMDLINE_FILE="/boot/cmdline.txt"
else
    warn "Could not find cmdline.txt"
    CMDLINE_FILE=""
fi

if [ -n "$CMDLINE_FILE" ]; then
    log "🔧 Removing console from cmdline.txt..."
    sudo cp "$CMDLINE_FILE" "${CMDLINE_FILE}.backup"
    sudo sed -i 's/console=serial0,[0-9]\+ //g' "$CMDLINE_FILE"
    sudo sed -i 's/console=ttyAMA0,[0-9]\+ //g' "$CMDLINE_FILE"
    sudo sed -i 's/console=ttyS0,[0-9]\+ //g' "$CMDLINE_FILE"
fi

# Double-check that serial console is still disabled (important for modem)
if [ -n "$CMDLINE_FILE" ] && grep -q "console=serial0\|console=ttyAMA0\|console=ttyS0" "$CMDLINE_FILE" 2>/dev/null; then
    warn "Serial console detected in cmdline.txt - removing again..."
    sudo sed -i 's/console=serial0,[0-9]\+ //g' "$CMDLINE_FILE"
    sudo sed -i 's/console=ttyAMA0,[0-9]\+ //g' "$CMDLINE_FILE"
    sudo sed -i 's/console=ttyS0,[0-9]\+ //g' "$CMDLINE_FILE"
fi

# Enable UART in config.txt
log "🔧 Enabling UART in config.txt..."
if ! grep -q "enable_uart=1" "$CONFIG_FILE"; then
    echo "enable_uart=1" | sudo tee -a "$CONFIG_FILE"
fi

log "📥 Downloading and compiling gsmMuxd..."
cd /tmp
sudo rm -rf gsmmux 2>/dev/null || true

# Download and compile gsmMuxd as per OZZMaker guide
sudo mkdir -p /usr/local/src
cd /usr/local/src
sudo rm -rf gsmmux 2>/dev/null || true
sudo git clone http://github.com/ozzmaker/gsmmux
cd gsmmux
sudo make
sudo cp gsmMuxd /usr/bin/gsmMuxd
sudo chmod +x /usr/bin/gsmMuxd

log "👥 Adding user to groups..."
sudo usermod -a -G tty,i2c,gpio,dialout $USER

# ===============================================
# STEP 2: Configure PPP Connection (OZZMaker Guide 2)
# ===============================================
echo
echo "=========================================="
log "📞 STEP 2: Configure PPP Connection"
echo "=========================================="

log "📁 Creating chatscripts directory..."
sudo mkdir -p /etc/ppp/chatscripts

log "📜 Creating mobile modem chat script..."
sudo tee /etc/ppp/chatscripts/mobile-modem.chat > /dev/null << 'EOF'
ABORT 'BUSY'
ABORT 'NO CARRIER'
ABORT 'VOICE'
ABORT 'NO DIALTONE'
ABORT 'NO DIAL TONE'
ABORT 'NO ANSWER'
ABORT 'DELAYED'
TIMEOUT 20
REPORT CONNECT
"" AT
OK ATH
OK ATZ
OK ATQ0
OK ATDT*99***1#
CONNECT ''
EOF

log "⚙️ Configuring PPP provider settings..."
sudo cp /etc/ppp/peers/provider /etc/ppp/peers/provider.backup 2>/dev/null || true

# Create the provider configuration file following OZZMaker guide
sudo tee /etc/ppp/peers/provider > /dev/null << EOF
# /etc/ppp/peers/provider
#
# This file describes a PPP connection to a provider
# via a serial port (physical or virtual)

# The chat script
connect "/usr/sbin/chat -v -f /etc/ppp/chatscripts/mobile-modem.chat -T $APN"

# The device to use  
/dev/ttyGSM0

# Serial port settings
115200
crtscts
lock
noauth
defaultroute
nodetach
usepeerdns
hide-password
persist
holdoff 10
maxfail 0
EOF

# ===============================================
# STEP 3: Configure GPS (OZZMaker Guide 3) 
# ===============================================
echo
echo "=========================================="
log "🛰️ STEP 3: Configure GPS"
echo "=========================================="

log "⚙️ Configuring GPSD..."
# Configure GPSD to use /dev/ttyGSM2 as per OZZMaker guide
sudo cp /etc/default/gpsd /etc/default/gpsd.backup 2>/dev/null || true

sudo tee /etc/default/gpsd > /dev/null << 'EOF'
# Default settings for the gpsd init script and the hotplug wrapper.

# Start the gpsd daemon automatically at boot time
START_DAEMON="true"

# Use USB hotplugging to add new USB devices automatically to the daemon
USBAUTO="true"

# Devices gpsd should collect to at boot time.
# They need to be read/writeable, either by user gpsd or the group dialout.
DEVICES="/dev/ttyGSM1"

# Other options you want to pass to gpsd
GPSD_OPTIONS="-n"
EOF

# Configure systemd service for gpsd
log "🔧 Configuring GPSD systemd service..."
sudo mkdir -p /etc/systemd/system/gpsd.service.d
sudo tee /etc/systemd/system/gpsd.service.d/override.conf > /dev/null << 'EOF'
[Service]
User=pi
EOF

# ===============================================
# STEP 4: Create Startup Scripts and Configuration
# ===============================================
echo
echo "=========================================="
log "🚀 STEP 4: Configure Startup Scripts"
echo "=========================================="

# Create modem initialization script
log "Creating modem initialization script..."
sudo tee /usr/local/bin/modem-complete-start.sh > /dev/null << 'EOF'
#!/bin/bash
# SARA-R5 Modem Complete Initialization Script

LOGFILE="/var/log/modem-start.log"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOGFILE"
}

log_message "=== Starting complete modem initialization ==="

# Always clean up first
log_message "Cleaning up any existing processes..."
sudo poff -a 2>/dev/null || true
sudo pkill -f pppd 2>/dev/null || true  
sudo pkill -f chat 2>/dev/null || true
sudo pkill -f gsmMuxd 2>/dev/null || true
sudo rm -f /var/lock/LCK..ttyGSM* 2>/dev/null || true

# Start gsmMuxd
log_message "Starting GSM multiplexer..."
sudo gsmMuxd

# Wait for GSM channels
log_message "Waiting for GSM channels..."
timeout=30
counter=0
while [ ! -c /dev/ttyGSM0 ] || [ ! -c /dev/ttyGSM1 ] || [ ! -c /dev/ttyGSM2 ]; do
    if [ $counter -ge $timeout ]; then
        log_message "ERROR: GSM channels not created after $timeout seconds"
        exit 1
    fi
    sleep 2
    counter=$((counter + 2))
done
log_message "GSM channels created successfully"

# Initialize GPS (commands sent to ttyGSM0, data received on ttyGSM2)
log_message "Initializing GPS..."
echo -e "AT+UGPS=1,4,67\r\n" > /dev/ttyGSM0
sleep 3

# Read GPS response (optional)
sudo timeout 3 cat /dev/ttyGSM2 > /tmp/gps_response 2>/dev/null || true
if [ -s /tmp/gps_response ]; then
    response=$(cat /tmp/gps_response | tr -d '\r' | grep -v '^$' | tail -1)
    log_message "GPS response: $response"
fi

# Start PPP connection
log_message "Starting PPP connection..."
sudo pon

# Wait and check PPP status
sleep 10
if ip addr show ppp0 &>/dev/null; then
    log_message "SUCCESS: PPP connection established"
    ip addr show ppp0 | grep inet | head -1 >> "$LOGFILE"
else
    log_message "PPP connection not yet established (may take a few moments)"
fi

log_message "=== Modem initialization completed ==="
EOF

sudo chmod +x /usr/local/bin/modem-complete-start.sh

# Configure network priority (cellular over WiFi)
log "Configuring network priority script..."
sudo tee /usr/local/bin/network-priority.sh > /dev/null << 'EOF'
#!/bin/bash
# Network priority script - ensures cellular is preferred over WiFi

# Wait for interfaces to be up
sleep 5

# Check if ppp0 exists and is up
if ip link show ppp0 &>/dev/null; then
    # Get current default route
    DEFAULT_ROUTE=$(ip route show default)
    
    # If default route is not via ppp0, fix it
    if ! echo "$DEFAULT_ROUTE" | grep -q "dev ppp0"; then
        # Remove WiFi default route
        ip route del default dev wlan0 2>/dev/null || true
        
        # Add cellular as default with higher priority
        PPP_GW=$(ip route show dev ppp0 | grep -o 'peer [0-9.]*' | cut -d' ' -f2)
        if [[ -n "$PPP_GW" ]]; then
            ip route add default via $PPP_GW dev ppp0 metric 100
        fi
        
        # Add WiFi as backup with lower priority
        WIFI_GW=$(ip route show dev wlan0 | grep -o 'via [0-9.]*' | cut -d' ' -f2 | head -1)
        if [[ -n "$WIFI_GW" ]]; then
            ip route add default via $WIFI_GW dev wlan0 metric 200
        fi
        
        logger "Network priority: Cellular (ppp0) set as primary, WiFi as backup"
    fi
fi
EOF

sudo chmod +x /usr/local/bin/network-priority.sh

# Configure NetworkManager to not manage ppp0
sudo tee /etc/NetworkManager/conf.d/99-unmanaged-devices.conf > /dev/null << EOF
[keyfile]
unmanaged-devices=interface-name:ppp0
EOF

# Set up logging
log "Setting up logging..."
sudo touch /var/log/modem-start.log
sudo chmod 644 /var/log/modem-start.log

# Set up log rotation
sudo tee /etc/logrotate.d/sara-r5 > /dev/null << EOF
/var/log/modem-start.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    copytruncate
}
EOF

# Add to user's crontab for automatic startup
log "Configuring automatic startup via crontab..."
(crontab -l 2>/dev/null | grep -v "modem-complete-start.sh"; echo "@reboot /usr/local/bin/modem-complete-start.sh") | crontab -

# ===============================================
# STEP 5: Create Testing Tools
# ===============================================
echo
echo "=========================================="
log "🛠️ STEP 5: Create Testing Tools"
echo "=========================================="

# GPS testing script
sudo tee /usr/local/bin/test-gps.sh > /dev/null << 'EOF'
#!/bin/bash
# GPS Test Script for SARA-R5

echo "SARA-R5 GPS Test"
echo "=================="

if [[ ! -c /dev/ttyGSM2 ]]; then
    echo "ERROR: GPS device /dev/ttyGSM2 not found"
    echo "Make sure gsmMuxd is running: sudo gsmMuxd"
    exit 1
fi

echo "Reading GPS data from /dev/ttyGSM2..."
echo "Press Ctrl+C to stop"
echo ""

timeout 30 cat /dev/ttyGSM2 || echo "No GPS data received in 30 seconds"
EOF

# PPP testing script
sudo tee /usr/local/bin/test-ppp.sh > /dev/null << 'EOF'
#!/bin/bash
# PPP Connection Test Script

echo "SARA-R5 PPP Connection Test"
echo "============================"

# Check if ppp0 exists
if ip addr show ppp0 &>/dev/null; then
    echo "✓ PPP interface (ppp0) is UP"
    ip addr show ppp0 | grep inet
    echo ""
    
    # Test connectivity
    echo "Testing internet connectivity via cellular..."
    if ping -I ppp0 -c 3 8.8.8.8 &>/dev/null; then
        echo "✓ Internet connectivity via cellular: WORKING"
    else
        echo "✗ Internet connectivity via cellular: FAILED"
    fi
else
    echo "✗ PPP interface (ppp0) not found"
    echo "Try running: sudo pon"
fi
EOF

# Status script
sudo tee /usr/local/bin/sara-r5-status.sh > /dev/null << 'EOF'
#!/bin/bash
# SARA-R5 System Status Script

echo "SARA-R5 LTE-M + GPS System Status"
echo "=================================="
echo ""

# Check gsmMuxd
if pgrep gsmMuxd > /dev/null; then
    echo "✓ gsmMuxd: RUNNING"
else
    echo "✗ gsmMuxd: NOT RUNNING"
fi

# Check GSM devices
echo ""
echo "GSM Multiplexed Devices:"
for dev in /dev/ttyGSM0 /dev/ttyGSM1 /dev/ttyGSM2; do
    if [[ -c "$dev" ]]; then
        target=$(readlink "$dev" 2>/dev/null || echo "direct")
        echo "  ✓ $dev -> $target"
    else
        echo "  ✗ $dev: NOT FOUND"
    fi
done

# Check PPP
echo ""
if ip addr show ppp0 &>/dev/null; then
    echo "✓ PPP Connection: ACTIVE"
    ip addr show ppp0 | grep inet | sed 's/^/  /'
else
    echo "✗ PPP Connection: INACTIVE"
fi

# Check I2C
echo ""
if [ -c /dev/i2c-1 ]; then
    echo "✓ I2C Interface: AVAILABLE (/dev/i2c-1)"
else
    echo "✗ I2C Interface: NOT AVAILABLE"
fi

# Check processes
echo ""
echo "Related Processes:"
ps aux | grep -E "(ppp|chat|gsmMuxd)" | grep -v grep | sed 's/^/  /'

# Show recent logs
echo ""
echo "Recent Modem Logs (last 5 lines):"
tail -5 /var/log/modem-start.log 2>/dev/null | sed 's/^/  /' || echo "  No logs found"
EOF

# I2C testing script
sudo tee /usr/local/bin/test-i2c.sh > /dev/null << 'EOF'
#!/bin/bash
# I2C Test Script for SARA-R5

echo "I2C Interface Test"
echo "=================="

if [[ ! -c /dev/i2c-1 ]]; then
    echo "ERROR: I2C device /dev/i2c-1 not found"
    echo "Make sure I2C is enabled: sudo raspi-config"
    exit 1
fi

echo "Scanning I2C bus for devices..."
sudo i2cdetect -y 1

echo ""
echo "Testing Python smbus import..."
python3 -c "import smbus; print('✓ smbus imported successfully')" 2>/dev/null || echo "✗ smbus import failed"
python3 -c "import smbus2; print('✓ smbus2 imported successfully')" 2>/dev/null || echo "✗ smbus2 import failed"
EOF

# Make scripts executable
sudo chmod +x /usr/local/bin/test-gps.sh
sudo chmod +x /usr/local/bin/test-ppp.sh
sudo chmod +x /usr/local/bin/sara-r5-status.sh
sudo chmod +x /usr/local/bin/test-i2c.sh

# Test I2C after a brief wait
sleep 2
if [ -c /dev/i2c-1 ]; then
    log "✅ I2C interface enabled successfully"
    log "📍 I2C device: /dev/i2c-1 is available"
else
    warn "I2C device /dev/i2c-1 not found - will be available after reboot"
fi

# ===============================================
# INSTALLATION COMPLETE
# ===============================================
echo
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║      SARA-R5 Installation Complete!         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Configuration Summary:${NC}"
echo "• GSM Multiplexer: gsmMuxd installed"
echo "• PPP Device: /dev/ttyGSM0 (cellular data)"
echo "• GPS Device: /dev/ttyGSM2 (GNSS data)"
echo "• I2C Interface: Enabled for sensors"
echo "• Auto-login: Enabled for user $USER"
echo "• Network Priority: Cellular first, WiFi backup"
echo "• APN: $APN"
echo "• Logs: /var/log/modem-start.log"
echo ""
echo -e "${YELLOW}Available Commands:${NC}"
echo "• sara-r5-status.sh     - Check system status"
echo "• test-ppp.sh          - Test cellular connection"
echo "• test-gps.sh          - Test GPS functionality"
echo "• test-i2c.sh          - Test I2C interface"
echo "• sudo pon             - Start PPP connection manually"
echo "• sudo poff            - Stop PPP connection"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Reboot the system: sudo reboot"
echo "2. After reboot, check status: sara-r5-status.sh"
echo "3. Test connectivity: test-ppp.sh"
echo "4. Test I2C: test-i2c.sh"
echo "5. Monitor logs: tail -f /var/log/modem-start.log"
echo ""
echo -e "${RED}IMPORTANT:${NC} A reboot is required for all changes to take effect!"
echo ""