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
APN="hologram"                        # Replace with your carrier's APN
PROVIDER_NAME="provider"              # Name for your provider (used in PPP peer config)

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

# Download and compile gsmMuxd as per OZZMaker guide
sudo mkdir -p /usr/local/src
cd /usr/local/src
sudo rm -rf gsmmux 2>/dev/null || true
sudo git clone https://github.com/ozzmaker/gsmmux
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

# ===============================================
# Create Scripts Following OZZMaker Methodology
# ===============================================
echo
echo "=========================================="
log "📜 Creating Control Scripts"
echo "=========================================="

# Create your exact working script with DNS fix
log "📄 Creating your working connection script..."
tee ~/ppp_connect.sh > /dev/null << 'EOF'
#!/bin/bash
# Start multiplexer first
sudo gsmMuxd
sleep 20
sudo pon

# Wait for PPP connection to establish
sleep 10

# Fix DNS for cellular connection (critical for mobile use)
echo "$(date): Configuring DNS for cellular..."
sudo chattr -i /etc/resolv.conf 2>/dev/null || true
sudo cp /etc/resolv.conf /etc/resolv.conf.backup 2>/dev/null || true
sudo tee /etc/resolv.conf > /dev/null << 'DNSEOF'
# DNS servers for cellular connection
nameserver 8.8.8.8
nameserver 8.8.4.4
nameserver 1.1.1.1
DNSEOF
sudo chattr +i /etc/resolv.conf

echo "$(date): PPP connection and DNS configured successfully"
EOF

chmod +x ~/ppp_connect.sh

# Create status checking script
log "📄 Creating status check script..."
tee ~/check_status.sh > /dev/null << 'EOF'
#!/bin/bash
# Status Check Script - OZZMaker SARA-R5

echo "=== OZZMaker SARA-R5 Status Check ==="
echo "Timestamp: $(date)"
echo

# Check gsmMuxd
echo "📡 Multiplexer Status:"
if pgrep gsmMuxd >/dev/null; then
    echo "✅ gsmMuxd running (PID: $(pgrep gsmMuxd))"
    if ls /dev/ttyGSM* >/dev/null 2>&1; then
        echo "✅ Virtual devices created:"
        ls -la /dev/ttyGSM*
    else
        echo "❌ No virtual devices found"
    fi
else
    echo "❌ gsmMuxd not running"
fi
echo

# Check PPP
echo "📞 PPP Status:"
if pgrep pppd >/dev/null; then
    echo "✅ pppd running (PID: $(pgrep pppd))"
    if ip link show ppp0 >/dev/null 2>&1; then
        echo "✅ PPP interface active:"
        ip addr show ppp0
    else
        echo "❌ No PPP interface"
    fi
else
    echo "❌ pppd not running"
fi
echo

# Check GPS
echo "🛰️ GPS Status:"
if systemctl is-active gpsd >/dev/null 2>&1; then
    echo "✅ gpsd service active"
else
    echo "❌ gpsd service not active"
fi

if [ -c "/dev/ttyGSM1" ]; then
    echo "✅ GPS device available (/dev/ttyGSM1)"
    echo "📡 Sample GPS data (5 seconds):"
    timeout 5 cat /dev/ttyGSM1 | head -5 | while read line; do
        if [[ "$line" =~ ^\$G ]]; then
            echo "   📍 $line"
        fi
    done 2>/dev/null || echo "   ⏳ No GPS data received (may need time to acquire fix)"
else
    echo "❌ GPS device not available"
fi
echo

# Test connectivity
echo "🌐 Connectivity Test:"
if ping -c 1 8.8.8.8 >/dev/null 2>&1; then
    echo "✅ Internet connectivity working"
else
    echo "❌ No internet connectivity"
fi
EOF

chmod +x ~/check_status.sh

# Create GPS test script
log "📄 Creating GPS monitoring script..."
tee ~/gps_monitor.sh > /dev/null << 'EOF'
#!/bin/bash
# GPS Monitor Script - OZZMaker SARA-R5

echo "=== GPS Monitor ==="
echo "Monitoring GPS data from /dev/ttyGSM1"
echo "Press Ctrl+C to stop"
echo

if [ -c "/dev/ttyGSM1" ]; then
    cat /dev/ttyGSM1 | while read line; do
        if [[ "$line" =~ ^\$G ]]; then
            echo "$(date '+%H:%M:%S') - $line"
        fi
    done
else
    echo "❌ GPS device /dev/ttyGSM1 not available"
    echo "Run ~/full_startup.sh first"
fi
EOF

chmod +x ~/gps_monitor.sh

# ===============================================
# Configure Auto-Start (Following OZZMaker)
# ===============================================
echo
echo "=========================================="
log "⏰ Configuring Auto-Start"
echo "=========================================="

log "🔧 Setting up cron job..."
# Remove any existing cron jobs for PPP connection
(crontab -l 2>/dev/null | grep -v ppp_connect) | crontab -

# Add your exact working cron job
(crontab -l 2>/dev/null; echo "@reboot /home/$USER/ppp_connect.sh") | crontab -

log "🔧 Enabling GPSD service..."
sudo systemctl daemon-reload
sudo systemctl enable gpsd

# ===============================================
# Final Setup and Instructions
# ===============================================
echo
echo "=========================================="
echo "🎉 Installation Complete!"
echo "=========================================="
echo
echo "📁 Created Scripts:"
echo "   ~/ppp_connect.sh    - Your working connection script"
echo "   ~/check_status.sh   - Check all services"
echo "   ~/gps_monitor.sh    - Monitor GPS data stream"
echo
echo "⚙️ Configuration Applied:"
echo "   ✅ Serial console disabled, UART enabled"
echo "   ✅ gsmMuxd compiled and installed"
echo "   ✅ PPP configured for /dev/ttyGSM0"
echo "   ✅ GPSD configured for /dev/ttyGSM1"
echo "   ✅ DNS configured for cellular connectivity"
echo "   ✅ Auto-start configured via cron"
echo "   ✅ User added to required groups"
echo
echo "📖 OZZMaker Guides Implemented:"
echo "   1. ✅ Multiplexing enabled"
echo "   2. ✅ PPP connection configured"
echo "   3. ✅ GPS streaming configured"
echo
echo "🚀 Next Steps:"
echo "   1. REBOOT the Raspberry Pi"
echo "   2. Wait 2-3 minutes after boot"
echo "   3. Run: ~/check_status.sh"
echo "   4. Test mobile connectivity away from WiFi"
echo "   5. Monitor GPS: ~/gps_monitor.sh"
echo
echo "🔧 Manual Commands:"
echo "   Start connection:   ~/ppp_connect.sh"
echo "   Stop PPP:           sudo poff"
echo "   Check status:       ~/check_status.sh"
echo "   Monitor GPS:        ~/gps_monitor.sh"
echo "   Use minicom:        minicom -D /dev/ttyGSM0"
echo
echo "📝 Customize APN:"
echo "   Edit APN variable at top of this script and re-run"
echo "   Current APN: $APN"
echo
warn "⚠️  IMPORTANT: You must REBOOT for all changes to take effect!"
warn "⚠️  After reboot, log out and back in for group permissions!"
echo
read -p "🔄 Reboot now? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log "🔄 Rebooting in 5 seconds..."
    sleep 5
    sudo reboot
else
    log "✅ Installation complete. Please reboot when ready."
    echo
    echo "After reboot, run: ~/check_status.sh"
fi