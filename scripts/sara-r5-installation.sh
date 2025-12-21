#!/bin/bash

# SARA-R5 Installation Script for Raspberry Pi Zero
# Username: proscout
# This script automates the installation and configuration of GSM, GPS, and IMU

set -e  # Exit on any error

echo "========================================="
echo "SARA-R5 Installation Script"
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

print_status "Starting SARA-R5 installation for user: $USER"

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

# Step 2: Install git
print_status "Step 2: Installing git..."
sudo apt-get update
sudo apt-get install -y git
print_status "Git installed successfully"

# Step 3: Install and configure gsmMuxd
print_status "Step 3: Installing gsmMuxd..."

# 3a: Configure raspi-config (serial)
print_status "Configuring serial interface..."
sudo raspi-config nonint do_serial 1  # Disable serial console
sudo raspi-config nonint do_serial_hw 0  # Enable serial hardware
print_status "Serial interface configured"

# 3b: Download and compile gsmMuxd
print_status "Downloading and compiling gsmMuxd..."
sudo mkdir -p /usr/local/src
cd /usr/local/src
sudo git clone https://github.com/ozzmaker/gsmmux
cd gsmmux
sudo make
sudo cp gsmMuxd /usr/bin/gsmMuxd
sudo chmod +x /usr/bin/gsmMuxd
cd ~
print_status "gsmMuxd compiled and installed"

# 3c: Add user to tty group
print_status "Adding proscout to tty group..."
sudo usermod -a -G tty proscout
print_status "User added to tty group"

# 3d: gsmMuxd will be started via cron script
print_status "gsmMuxd will be started via cron startup script"

# Step 4: Configure PPP
print_status "Step 4: Configuring PPP..."

# 4a: Install PPP
print_status "Installing PPP..."
sudo apt-get install -y ppp
print_status "PPP installed"

# 4b: Create chatscript directory and file
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
prompt_user "Enter your APN" APN "net.hotm"

# 4c: Configure PPP provider
print_status "Configuring PPP provider..."
sudo cp /etc/ppp/peers/provider /etc/ppp/peers/provider.backup

# Create new provider configuration (FIXED: removed unsupported 'metric' option)
sudo tee /etc/ppp/peers/provider > /dev/null << EOF
# /etc/ppp/peers/provider
#
# Configuration file for pppd to connect to cellular network

# The chat script
connect "/usr/sbin/chat -v -f /etc/ppp/chatscripts/mobile-modem.chat -T $APN"

# Serial device
/dev/ttyGSM1

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

# Add user to dialout group
print_status "Adding proscout to dip group..."
sudo usermod -a -G dip proscout
print_status "User added to dip group"

# Create PPP start script (kept for manual use)
print_status "Creating PPP startup script..."
tee ~/pppStart.sh > /dev/null << 'EOF'
#!/bin/bash
sleep 5
pon

# Wait for ppp0 interface to come up
sleep 10

# Add WiFi backup route (PPP priority is handled by provider file)
WIFI_GATEWAY=$(ip route | grep wlan0 | grep -E "^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+" | awk '{print $9}' | head -1)
if [ ! -z "$WIFI_GATEWAY" ]; then
    sudo ip route add default via $WIFI_GATEWAY dev wlan0 metric 200 2>/dev/null || true
    echo "WiFi backup route added (metric 200)"
fi
EOF

chmod +x ~/pppStart.sh

# PPP startup will be handled by sara_r5_startup.sh

# Step 5: Configure GPS
print_status "Step 5: Configuring GPS..."

# Install minicom
print_status "Installing minicom..."
sudo apt-get install -y minicom
print_status "Minicom installed"

# Create GPS configuration script for initial setup
print_status "Creating GPS initial configuration script..."
tee ~/configure_gps_initial.sh > /dev/null << 'EOF'
#!/bin/bash
# GPS Initial Configuration Script (Run ONCE after first boot)
# This configures the persistent GPS settings on SARA-R5

echo "Configuring SARA-R5 for GPS (initial setup)..."
echo "This configures persistent settings - only needs to be run ONCE"

# Wait for GSM mux to be available
echo "Waiting for GSM multiplexer..."
timeout=30
while [ $timeout -gt 0 ]; do
    if [ -e /dev/ttyGSM0 ]; then
        echo "GSM multiplexer available"
        break
    fi
    sleep 1
    timeout=$((timeout-1))
done

if [ $timeout -eq 0 ]; then
    echo "ERROR: GSM multiplexer not available"
    exit 1
fi

# Function to send AT command
send_at_command() {
    echo "Sending: $1"
    echo -e "$1\r" > /dev/ttyGSM0
    sleep 3
}

# Configure PERSISTENT GPS settings (only need to run once)
echo "Configuring persistent GPS settings..."
send_at_command "AT+UGPRF=2"    # Route GNSS data through multiplexer (persistent)
send_at_command "AT+USIO=2"     # Configure dataflow variant (persistent)  
send_at_command "AT+UGRMC=1"    # Store RMC NMEA sentences (persistent)
send_at_command "AT+UGGLL=1"    # Store GLL NMEA sentences (persistent)
send_at_command "AT+UGGSV=1"    # Store GSV NMEA sentences (persistent)
send_at_command "AT+UGGGA=1"    # Store GGA NMEA sentences (persistent)

echo ""
echo "========================================="
echo "GPS initial configuration completed!"
echo "========================================="
echo "These settings are now stored permanently"
echo "You only need to run this script ONCE"
echo ""
echo "To start GPS on each boot, the startup script will run:"
echo "  AT+UGIND=1  (activate unsolicited aiding result)"
echo ""
EOF

chmod +x ~/configure_gps_initial.sh
print_status "GPS configuration script created"

# Step 6: Configure IMU (I2C)
print_status "Step 6: Configuring IMU (I2C)..."
sudo raspi-config nonint do_i2c 0  # Enable I2C
print_status "I2C enabled for IMU"

# Create a SIMPLE startup script (based on what actually works)
print_status "Creating simple startup script..."
tee ~/sara_r5_startup.sh > /dev/null << 'EOF'
#!/bin/bash
# SARA-R5 Simple Startup Script
# This script starts all SARA-R5 services in the correct order

LOG_FILE="/home/proscout/sara_r5_startup.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "========================================="
echo "$(date): Starting SARA-R5 services..."
echo "========================================="

# Wait for system to fully boot
echo "$(date): Waiting for system to stabilize..."
sleep 15

# Start GSM Multiplexer
echo "$(date): Starting GSM Multiplexer..."
sudo /usr/bin/gsmMuxd &
sleep 10

# Configure GPS (non-persistent settings)
echo "$(date): Configuring GPS..."
echo -e "AT+UGIND=1\r" > /dev/ttyGSM0 2>/dev/null || true

# Start GPS (power state is not persistent)
echo "$(date): Starting GPS..."
echo -e "AT+UGPS=1,0,67\r" > /dev/ttyGSM0 2>/dev/null || true

# Start PPP
echo "$(date): Starting PPP connection..."
pon

echo "$(date): SARA-R5 startup completed"
echo "========================================="
EOF

chmod +x ~/sara_r5_startup.sh

# Add startup script to cron (this is the ONLY cron entry needed)
print_status "Adding startup script to cron..."
(crontab -l 2>/dev/null; echo "@reboot /home/proscout/sara_r5_startup.sh" | grep -v "pppStart\|configure_gps") | crontab -

# Create useful utility scripts
print_status "Creating utility scripts..."

# Script to manually set network priority
tee ~/set_network_priority.sh > /dev/null << 'EOF'
#!/bin/bash
# Manually set network priority: PPP > WiFi

echo "Setting network priority: PPP > WiFi"

if ip route | grep -q "ppp0"; then
    # Remove existing default routes
    sudo ip route del default dev wlan0 2>/dev/null || true
    sudo ip route del default dev ppp0 2>/dev/null || true
    
    # Set PPP as primary with lower metric (higher priority)
    sudo ip route add default dev ppp0 metric 100
    echo "PPP set as primary connection (metric 100)"
    
    # Set WiFi as backup with higher metric (lower priority)  
    WIFI_GATEWAY=$(ip route | grep wlan0 | grep -v default | grep -E "^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+" | awk '{print $9}' | head -1)
    if [ ! -z "$WIFI_GATEWAY" ]; then
        sudo ip route add default via $WIFI_GATEWAY dev wlan0 metric 200
        echo "WiFi set as backup connection (metric 200)"
    fi
else
    echo "PPP connection not available"
    exit 1
fi

echo "Network priority configured successfully"
ip route show default
EOF
chmod +x ~/set_network_priority.sh

# Script to check GPS data
tee ~/check_gps.sh > /dev/null << 'EOF'
#!/bin/bash
echo "Checking GPS data on /dev/ttyGSM2..."
echo "Press Ctrl+C to exit"
cat /dev/ttyGSM2
EOF
chmod +x ~/check_gps.sh

# Script to check connection status
tee ~/check_connection.sh > /dev/null << 'EOF'
#!/bin/bash
echo "=== PPP Connection Status ==="
ip route | grep ppp0 && echo "PPP connection active" || echo "PPP connection inactive"
echo ""
echo "=== Network interfaces ==="
ip addr show
echo ""
echo "=== Routing Table (Priority Order) ==="
ip route show | sort -k9 -n
echo ""
echo "=== Default Routes by Priority ==="
ip route show default | sort -k9 -n
echo ""
echo "=== GSM Multiplexer Status ==="
pgrep -x "gsmMuxd" > /dev/null && echo "gsmMuxd is running" || echo "gsmMuxd is not running"
echo ""
echo "=== Internet Connectivity Test ==="
echo "Testing via PPP..."
ping -c 2 -I ppp0 8.8.8.8 2>/dev/null && echo "PPP: OK" || echo "PPP: Failed"
echo "Testing via WiFi..."
ping -c 2 -I wlan0 8.8.8.8 2>/dev/null && echo "WiFi: OK" || echo "WiFi: Failed"
EOF
chmod +x ~/check_connection.sh

print_status "========================================="
print_status "Installation completed successfully!"
print_status "========================================="
echo ""
print_status "Created utility scripts:"
echo "  ~/check_gps.sh              - Monitor GPS data"
echo "  ~/check_connection.sh       - Check connection status"
echo "  ~/configure_gps_initial.sh  - Initial GPS setup (run ONCE after first boot)"
echo "  ~/pppStart.sh               - Start PPP connection manually"
echo "  ~/sara_r5_startup.sh        - Simple startup sequence (runs on boot)"
echo "  ~/set_network_priority.sh   - Manually fix network priority"
echo ""
print_warning "IMPORTANT SETUP STEPS:"
print_warning "1. Reboot the system to apply all changes"
print_warning "2. After first boot, run: ~/configure_gps_initial.sh (ONLY ONCE)"
print_warning "3. After that, services will start automatically on every boot"
echo ""
print_status "Your APN is configured as: $APN"
print_status "GPS data will be available on: /dev/ttyGSM2"
print_status "AT commands can be sent to: /dev/ttyGSM0"
print_status "PPP connection will use: /dev/ttyGSM1"
echo ""

read -p "Would you like to reboot now? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_status "Rebooting system..."
    sudo reboot
else
    print_warning "Please reboot manually to complete the setup"
fi