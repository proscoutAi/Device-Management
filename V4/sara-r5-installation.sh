#!/bin/bash

# SARA-R5 Installation Script for Raspberry Pi Zero
# Username: proscout
# Simple setup - MODEM ONLY (no GPS, no multiplexing)

set -e  # Exit on any error

echo "========================================="
echo "SARA-R5 Simple Installation Script"
echo "Modem Only - No GPS or Multiplexing"
echo "========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to prompt user for input
prompt_user() {
    local prompt="$1"
    local var_name="$2"
    local default="$3"
    
    if [ -n "$default" ]; then
        read -p "$prompt [$default]: " input
        eval $var_name=\"${input:-$default}\"
    else
        read -p "$prompt: " input
        eval $var_name=\"$input\"
    fi
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    print_error "Please run this script as user 'proscout', not as root"
    exit 1
fi

# Verify username
if [ "$USER" != "proscout" ]; then
    print_error "This script should be run as user 'proscout'"
    exit 1
fi

print_status "Starting SARA-R5 modem installation for user: $USER"

# Step 1: Configure automatic login
print_status "Step 1: Configuring automatic login for user proscout..."
sudo systemctl set-default multi-user.target
sudo ln -sf /etc/systemd/system/getty.target.wants/getty@tty1.service /etc/systemd/system/getty.target.wants/getty@tty1.service
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d/
sudo tee /etc/systemd/system/getty@tty1.service.d/override.conf > /dev/null << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin proscout --noclear %I \$TERM
EOF
print_status "Automatic login configured"

# Step 2: Install required packages
print_status "Step 2: Installing required packages..."
sudo apt-get update
sudo apt-get install -y git ppp minicom
print_status "Required packages installed successfully"

# Step 3: Configure serial interface
print_status "Step 3: Configuring serial interface..."
sudo raspi-config nonint do_serial 1  # Disable serial console
sudo raspi-config nonint do_serial_hw 0  # Enable serial hardware
print_status "Serial interface configured for /dev/ttyS0"

# Step 4: Configure PPP
print_status "Step 4: Configuring PPP..."

# Create chatscript directory and file
print_status "Creating PPP chatscript..."
sudo mkdir -p /etc/ppp/chatscripts/
sudo tee /etc/ppp/chatscripts/mobile-modem.chat > /dev/null << 'EOF'
ABORT 'BUSY'
ABORT 'NO CARRIER'
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
print_status "Chatscript created"

# Get APN from user
prompt_user "Enter your APN" APN "hologram"

# Configure PPP provider
print_status "Configuring PPP provider..."
sudo cp /etc/ppp/peers/provider /etc/ppp/peers/provider.backup 2>/dev/null || true

# Create new provider configuration using /dev/ttyS0
sudo tee /etc/ppp/peers/provider > /dev/null << EOF
# /etc/ppp/peers/provider
# Configuration file for pppd to connect to cellular network

# The chat script
connect "/usr/sbin/chat -v -f /etc/ppp/chatscripts/mobile-modem.chat -T $APN"

# Serial device (direct UART connection)
/dev/ttyS0

# Speed of the serial line
115200

# Assumes that your IP address is allocated dynamically by the ISP
noipdefault

# Try to get the name server addresses from the ISP
usepeerdns

# Use this connection as the default route with higher priority
defaultroute
replacedefaultroute

# Makes pppd "dial again" when the connection is lost
persist

# Do not ask the remote to authenticate
noauth

# No hardware flow control on the serial link with the modem
nocrtscts

# No modem control lines
local

# Compression
novj
novjccomp
nobsdcomp
nopcomp
noaccomp

# The phone is not required to authenticate
noauth

# Debug info
debug
EOF

# Add user to dialout and dip groups
print_status "Adding proscout to required groups..."
sudo usermod -a -G dialout,dip proscout
print_status "User added to dialout and dip groups"

# Step 5: Configure IMU (I2C only)
print_status "Step 5: Configuring I2C for sensors..."
sudo raspi-config nonint do_i2c 0  # Enable I2C
print_status "I2C enabled for sensors"

# Create simple startup script
print_status "Creating startup script..."
tee ~/sara_r5_startup.sh > /dev/null << 'EOF'
#!/bin/bash
# SARA-R5 Simple Startup Script - Modem Only
# This script starts PPP connection using /dev/ttyS0

LOG_FILE="/home/proscout/sara_r5_startup.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "========================================="
echo "$(date): Starting SARA-R5 modem services..."
echo "========================================="

# Wait for system to fully boot
echo "$(date): Waiting for system to stabilize..."
sleep 15

# Wait for /dev/ttyS0 to be available
echo "$(date): Waiting for /dev/ttyS0..."
timeout=30
while [ $timeout -gt 0 ]; do
    if [ -e /dev/ttyS0 ]; then
        echo "$(date): /dev/ttyS0 is available"
        break
    fi
    sleep 1
    timeout=$((timeout-1))
done

if [ $timeout -eq 0 ]; then
    echo "$(date): ERROR: /dev/ttyS0 not available"
    exit 1
fi

# Start PPP connection
echo "$(date): Starting PPP connection..."
pon

# Wait for PPP to establish connection
sleep 10

# Check if PPP connection is up
if ip link show ppp0 > /dev/null 2>&1; then
    echo "$(date): PPP connection established successfully"
    
    # Set cellular as default route with highest priority
    echo "$(date): Configuring network priority (cellular > WiFi)..."
    
    # Remove any existing default routes for clean setup
    sudo ip route del default dev wlan0 2>/dev/null || true
    sudo ip route del default dev ppp0 2>/dev/null || true
    
    # Add cellular as primary (metric 100)
    sudo ip route add default dev ppp0 metric 100 2>/dev/null || true
    
    # Add WiFi as backup (metric 600) if available
    WIFI_GATEWAY=$(ip route | grep wlan0 | grep -v default | awk '/^[0-9]/ {print $3}' | head -1)
    if [ ! -z "$WIFI_GATEWAY" ]; then
        sudo ip route add default via $WIFI_GATEWAY dev wlan0 metric 600 2>/dev/null || true
        echo "$(date): WiFi backup route added (metric 600)"
    fi
    
    echo "$(date): Network priority configured: Cellular (primary) > WiFi (backup)"
else
    echo "$(date): WARNING: PPP connection failed to establish"
fi

echo "$(date): SARA-R5 startup completed"
echo "========================================="
EOF

chmod +x ~/sara_r5_startup.sh

# Add startup script to cron
print_status "Adding startup script to cron..."
(crontab -l 2>/dev/null | grep -v "sara_r5_startup\|pppStart\|configure_gps"; echo "@reboot /home/proscout/sara_r5_startup.sh") | crontab -

# Create utility scripts
print_status "Creating utility scripts..."

# Script to manually start PPP
tee ~/start_ppp.sh > /dev/null << 'EOF'
#!/bin/bash
echo "Starting PPP connection manually..."
pon
sleep 5
if ip link show ppp0 > /dev/null 2>&1; then
    echo "PPP connection established"
    # Set network priority
    sudo ip route add default dev ppp0 metric 100 2>/dev/null || true
    echo "Network priority set: PPP > WiFi"
    ip route show default
else
    echo "PPP connection failed"
fi
EOF
chmod +x ~/start_ppp.sh

# Script to stop PPP
tee ~/stop_ppp.sh > /dev/null << 'EOF'
#!/bin/bash
echo "Stopping PPP connection..."
poff
echo "PPP connection stopped"
EOF
chmod +x ~/stop_ppp.sh

# Script to test modem AT commands
tee ~/test_modem.sh > /dev/null << 'EOF'
#!/bin/bash
echo "Testing modem AT commands on /dev/ttyS0..."
echo "Note: This will temporarily interfere with PPP if it's running"
echo "Press Ctrl+C to exit"
echo ""
echo "Sending AT command..."
timeout 5 bash -c 'echo "AT" > /dev/ttyS0 && cat /dev/ttyS0' 2>/dev/null || echo "Unable to communicate (PPP may be using the port)"
EOF
chmod +x ~/test_modem.sh

# Script to check connection status
tee ~/check_connection.sh > /dev/null << 'EOF'
#!/bin/bash
echo "=== SARA-R5 Connection Status ==="
echo ""
echo "=== PPP Connection ==="
if ip link show ppp0 > /dev/null 2>&1; then
    echo "✓ PPP connection active"
    ip addr show ppp0 | grep "inet "
else
    echo "✗ PPP connection inactive"
fi
echo ""
echo "=== Network Interfaces ==="
ip addr show | grep -E "^[0-9]+:|inet " | grep -A1 -E "wlan0|ppp0|eth0"
echo ""
echo "=== Routing Table (by Priority) ==="
ip route show default | sort -k9 -n
echo ""
echo "=== Connectivity Tests ==="
echo "Testing cellular (if available)..."
if ip link show ppp0 > /dev/null 2>&1; then
    ping -c 2 -I ppp0 8.8.8.8 2>/dev/null && echo "✓ Cellular: OK" || echo "✗ Cellular: Failed"
else
    echo "- Cellular: Not available"
fi

echo "Testing WiFi (if available)..."
if ip link show wlan0 > /dev/null 2>&1 && ip addr show wlan0 | grep -q "inet "; then
    ping -c 2 -I wlan0 8.8.8.8 2>/dev/null && echo "✓ WiFi: OK" || echo "✗ WiFi: Failed"
else
    echo "- WiFi: Not available"
fi

echo "Testing default route..."
ping -c 2 8.8.8.8 2>/dev/null && echo "✓ Default: OK" || echo "✗ Default: Failed"
EOF
chmod +x ~/check_connection.sh

print_status "========================================="
print_status "Installation completed successfully!"
print_status "========================================="
echo ""
print_status "Configuration Summary:"
echo "  • Modem device: /dev/ttyS0"
echo "  • PPP interface: ppp0 (when connected)"
echo "  • APN configured: $APN"
echo "  • Priority: Cellular > WiFi"
echo ""
print_status "Created utility scripts:"
echo "  ~/start_ppp.sh         - Start PPP connection manually"
echo "  ~/stop_ppp.sh          - Stop PPP connection"
echo "  ~/test_modem.sh        - Test AT commands (stop PPP first)"
echo "  ~/check_connection.sh  - Check connection status"
echo "  ~/sara_r5_startup.sh   - Startup script (runs on boot)"
echo ""
print_status "After reboot, the system will:"
echo "  1. Wait for system to stabilize (15 seconds)"
echo "  2. Start PPP connection on /dev/ttyS0"
echo "  3. Set cellular as primary internet"
echo "  4. Keep WiFi as backup connection"
echo ""
print_warning "IMPORTANT NOTES:"
print_warning "• PPP and your application cannot use /dev/ttyS0 simultaneously"
print_warning "• To test AT commands, stop PPP first: ~/stop_ppp.sh"
print_warning "• To restart PPP: ~/start_ppp.sh"
print_warning "• Check status anytime: ~/check_connection.sh"
echo ""

read -p "Would you like to reboot now to test the setup? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_status "Rebooting system..."
    sudo reboot
else
    print_warning "Please reboot manually to complete the setup: sudo reboot"
fi