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

log "📦 Installing required packages..."
sudo apt install -y ppp minicom gpsd gpsd-clients

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

# Enable UART in config.txt
log "🔧 Enabling UART in config.txt..."
if [ -f /boot/firmware/config.txt ]; then
    CONFIG_FILE="/boot/firmware/config.txt"
elif [ -f /boot/config.txt ]; then
    CONFIG_FILE="/boot/config.txt"
else
    error "Could not find config.txt"
fi

if ! grep -q "enable_uart=1" "$CONFIG_FILE"; then
    echo "enable_uart=1" | sudo tee -a "$CONFIG_FILE"
fi

log "📥 Downloading and compiling gsmMuxd..."
cd /tmp
sudo rm -rf gsmmux 2>/dev/null || true

sudo apt install git

# Download and compile gsmMuxd as per OZZMaker guide
sudo mkdir -p /usr/local/src
cd /usr/local/src
sudo rm -rf gsmmux 2>/dev/null || true
sudo git clone http://github.com/ozzmaker/gsmmux
cd gsmmux
sudo make
sudo cp gsmMuxd /usr/bin/gsmMuxd
sudo chmod +x /usr/bin/gsmMuxd

log "👥 Adding user to tty group..."
sudo usermod -a -G tty $USER

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

log "👥 Adding user to dialout group..."
sudo usermod -a -G dialout $USER

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

log "👥 Adding user to tty group (for GPSD)..."
sudo usermod -a -G tty $USER

#!/bin/bash
# SARA-R5 LTE-M + GPS Installation Script for Raspberry Pi Zero
# Based on OzzMaker configuration guides and proven working setup
# 
# This script configures:
# 1. gsmMuxd for serial multiplexing
# 2. PPP cellular connection on ttyGSM1 (priority over WiFi)
# 3. GPS reading on ttyGSM2
# 4. Automatic startup via cron
# 5. Logging setup

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/var/log/sara_r5_install.log"
APN="net.hotm"  # Change this to your carrier's APN

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | sudo tee -a "$LOG_FILE"
    echo -e "${GREEN}[INSTALL]${NC} $1"
}

log_error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: $1" | sudo tee -a "$LOG_FILE"
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warning() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - WARNING: $1" | sudo tee -a "$LOG_FILE"
    echo -e "${YELLOW}[WARNING]${NC} $1"
}



backup_file() {
    local file="$1"
    if [[ -f "$file" ]]; then
        sudo cp "$file" "$file.backup.$(date +%Y%m%d_%H%M%S)"
        log_message "Backed up $file"
    fi
}

# Get user input for APN
get_user_input() {
    echo -e "${YELLOW}SARA-R5 LTE-M + GPS Setup${NC}"
    echo "This script will configure your Raspberry Pi for cellular connectivity with GPS"
    echo ""
    
    read -p "Enter your carrier's APN (e.g., internet, broadband): " user_apn
    if [[ -n "$user_apn" ]]; then
        APN="$user_apn"
    fi
    
    read -p "Enter the username for non-root user (default: pi): " username
    if [[ -z "$username" ]]; then
        username="pi"
    fi
    
    if ! id "$username" &>/dev/null; then
        log_error "User '$username' does not exist"
        exit 1
    fi
    
    echo ""
    log_message "Configuration: APN=$APN, User=$username"
    echo ""
}

# Update system and install dependencies
install_dependencies() {
    log_message "Updating system and installing dependencies..."
    
    sudo apt update
    sudo apt upgrade -y
    
    # Install required packages
    sudo apt install -y \
        build-essential \
        git \
        ppp \
        wvdial \
        minicom \
        python3 \
        python3-pip \
        python3-venv \
        curl \
        wget
    
    log_message "Dependencies installed successfully"
}


# Configure PPP for cellular connection
configure_ppp() {
    log_message "Configuring PPP for cellular connection..."
    
    # Create PPP provider configuration
    sudo tee /etc/ppp/peers/provider > /dev/null << EOF
# PPP Provider configuration for SARA-R5 LTE-M
# Device: ttyGSM1 (multiplexed channel for data)
/dev/ttyGSM1
115200
crtscts
modem
noauth
noipdefault
usepeerdns
defaultroute
persist
maxfail 3
holdoff 10
connect "/usr/sbin/chat -v -f /etc/ppp/chatscripts/mobile-modem.chat -T $APN"
disconnect "/usr/sbin/chat -v -f /etc/ppp/chatscripts/mobile-disconnect.chat"
EOF

    # Create chat script for connection
    sudo mkdir -p /etc/ppp/chatscripts
    sudo tee /etc/ppp/chatscripts/mobile-modem.chat > /dev/null << 'EOF'
TIMEOUT 20
ABORT 'BUSY'
ABORT 'NO CARRIER'
ABORT 'VOICE'
ABORT 'NO DIALTONE'
ABORT 'NO DIAL TONE'
ABORT 'NO ANSWER'
ABORT 'DELAYED'
REPORT CONNECT
'' AT
OK ATH
OK ATZ
OK ATQ0
OK 'ATDT*99***1#'
CONNECT ''
EOF

    # Create disconnect script
    sudo tee /etc/ppp/chatscripts/mobile-disconnect.chat > /dev/null << 'EOF'
TIMEOUT 5
ABORT "ERROR"
ABORT "NO DIALTONE"
"" "ATH"
"" "ATZ"
EOF

    log_message "PPP configuration created"
}

# Configure serial interface
configure_serial() {
    log_message "Configuring serial interface..."
    
    # Enable UART in config.txt
    backup_file /boot/firmware/config.txt
    
    # Remove any existing UART configurations
    sudo sed -i '/enable_uart/d' /boot/firmware/config.txt
    sudo sed -i '/dtoverlay=disable-bt/d' /boot/firmware/config.txt
    
    # Add UART configuration using tee instead of cat
    echo "
# SARA-R5 Serial Configuration
enable_uart=1
dtoverlay=disable-bt" | sudo tee -a /boot/firmware/config.txt > /dev/null

    # Disable serial console
    backup_file /boot/firmware/cmdline.txt
    sudo sed -i 's/console=serial0,115200 //' /boot/firmware/cmdline.txt
    
    # Disable getty on serial
    sudo systemctl disable serial-getty@ttyS0.service 2>/dev/null || true
    sudo systemctl disable serial-getty@ttyAMA0.service 2>/dev/null || true
    
    log_message "Serial interface configured"
}

# Create modem initialization script
create_modem_script() {
    log_message "Creating modem initialization script..."
    
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
    log_message "Modem initialization script created"
}

# Configure network priority (cellular over WiFi)
configure_network_priority() {
    log_message "Configuring network priority (cellular first, WiFi backup)..."
    
    # Configure NetworkManager to not manage ppp0
    sudo cat > /etc/NetworkManager/conf.d/99-unmanaged-devices.conf << EOF
[keyfile]
unmanaged-devices=interface-name:ppp0
EOF

    # Set up routing script for network priority
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
    sudo log_message "Network priority configuration created"
}

# Set up logging
setup_logging() {
    log_message "Setting up logging directories and permissions..."
    
    # Create log files with proper permissions
    sudo touch /var/log/modem-start.log
    sudo touch /var/log/proscout.log
    
    # Set permissions for the specified user
    sudo chown root:root /var/log/modem-start.log
    sudo chown $username:$username /var/log/proscout.log
    sudo chmod 644 /var/log/modem-start.log
    sudo chmod 644 /var/log/proscout.log
    
    # Set up log rotation
    sudo tee /etc/logrotate.d/sara-r5 > /dev/null << EOF
/var/log/modem-start.log /var/log/proscout.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    copytruncate
}
EOF

    log_message "Logging setup completed"
}

# Configure automatic startup
configure_startup() {
    log_message "Configuring automatic startup..."
    
    # Add to user's crontab
    sudo -u $username bash << EOF
# Remove any existing entries
crontab -l 2>/dev/null | grep -v "modem-complete-start.sh" | crontab -

# Add new entry
(crontab -l 2>/dev/null; echo "@reboot /usr/local/bin/modem-complete-start.sh") | crontab -
EOF

    # Create systemd service as backup method
    sudo tee /etc/systemd/system/sara-r5-modem.service > /dev/null << EOF
[Unit]
Description=SARA-R5 LTE-M Modem Initialization
After=multi-user.target
Wants=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/modem-complete-start.sh
StandardOutput=journal
StandardError=journal
User=root
Group=root

[Install]
WantedBy=multi-user.target
EOF

    # Enable the service (disabled by default, cron is primary method)
    # systemctl enable sara-r5-modem.service
    
    log_message "Startup configuration completed"
}

# Create testing tools
create_testing_tools() {
    log_message "Creating testing and diagnostic tools..."
    
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

# Check processes
echo ""
echo "Related Processes:"
ps aux | grep -E "(ppp|chat|gsmMuxd)" | grep -v grep | sed 's/^/  /'

# Show recent logs
echo ""
echo "Recent Modem Logs (last 5 lines):"
tail -5 /var/log/modem-start.log 2>/dev/null | sed 's/^/  /' || echo "  No logs found"
EOF

    # Make scripts executable
    sudo chmod +x /usr/local/bin/test-gps.sh
    sudo chmod +x /usr/local/bin/test-ppp.sh
    sudo chmod +x /usr/local/bin/sara-r5-status.sh
    
    log_message "Testing tools created"
}

# Display completion message
show_completion_message() {
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║         SARA-R5 Installation Complete!      ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}Configuration Summary:${NC}"
    echo "• GSM Multiplexer: gsmMuxd installed"
    echo "• PPP Device: /dev/ttyGSM1 (cellular data)"
    echo "• GPS Device: /dev/ttyGSM2 (GNSS data)"
    echo "• Network Priority: Cellular first, WiFi backup"
    echo "• APN: $APN"
    echo "• Logs: /var/log/modem-start.log & /var/log/proscout.log"
    echo ""
    echo -e "${YELLOW}Available Commands:${NC}"
    echo "• sara-r5-status.sh     - Check system status"
    echo "• test-ppp.sh          - Test cellular connection"
    echo "• test-gps.sh          - Test GPS functionality"
    echo "• sudo pon             - Start PPP connection manually"
    echo "• sudo poff            - Stop PPP connection"
    echo ""
    echo -e "${YELLOW}Next Steps:${NC}"
    echo "1. Reboot the system: sudo reboot"
    echo "2. After reboot, check status: sara-r5-status.sh"
    echo "3. Test connectivity: test-ppp.sh"
    echo "4. Monitor logs: tail -f /var/log/modem-start.log"
    echo ""
    echo -e "${RED}IMPORTANT:${NC} A reboot is required for all changes to take effect!"
    echo ""
}

# Main installation process
main() {
    echo "Starting SARA-R5 Installation..."
    
    get_user_input
    
    log_message "Starting SARA-R5 LTE-M + GPS installation"
    
    install_dependencies
    
    configure_serial
    configure_ppp
    create_modem_script
    configure_network_priority
    setup_logging
    configure_startup
    create_testing_tools
    
    log_message "Installation completed successfully"
    show_completion_message
}

# Run main function
main "$@"