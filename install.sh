#!/bin/bash

# Complete installation script for Device Management software
# For Raspberry Pi 5 - Updated with Pi 5 optimizations and cellular modem setup
# Merged version with enhanced permissions and PolicyKit support

# Define colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "Please run as root or with sudo"
    exit 1
fi

# Configuration
SOFTWARE_NAME="device-manager"
SERVICE_USER="proscout"
USER_HOME="/home/${SERVICE_USER}"
INSTALL_DIR="${USER_HOME}/ProScout-master"
DEVICE_DIR="${INSTALL_DIR}/device-manager"
VENV_DIR="${INSTALL_DIR}/ProScout-Device"
LOGS_DIR="${INSTALL_DIR}/logs"
SCRIPTS_DIR="${INSTALL_DIR}/scripts"

# Get current directory
CURRENT_DIR=$(pwd)

print_status "Starting Device Manager installation for Raspberry Pi 5..."

# Create user if doesn't exist and add to required groups
if ! id "${SERVICE_USER}" &>/dev/null; then
    print_status "Creating ${SERVICE_USER} user..."
    useradd -m -s /bin/bash "${SERVICE_USER}"
    # Disable password for service account (security best practice)
    passwd -d "${SERVICE_USER}"
else
    print_status "User ${SERVICE_USER} already exists."
fi

# Make sure the user is in the required groups for GPIO, camera, and device access
print_status "Adding user to required groups..."
usermod -aG video,dialout,gpio,i2c,spi,tty "${SERVICE_USER}"

# Install system dependencies - Pi 5 optimized (removed pigpio, added lgpio)
print_status "Installing system dependencies for Pi 5..."
apt update
apt install -y python3-pip python3-venv python3-dev python3-opencv git curl unzip uuid-runtime \
    python3-gpiozero python3-lgpio lgpio python3-libgpiod gpiod i2c-tools modemmanager \
    modemmanager-dev libmm-glib-dev gpsd gpsd-clients libgps-dev screen network-manager \
    libqmi-utils policykit-1 python3-dbus libdbus-1-dev dbus python3-gi python3-gi-dev

# Set up GPIO permissions and libraries for Pi 5
print_status "Setting up GPIO for Pi 5..."

# Create GPIO permissions rule
cat > /etc/udev/rules.d/99-gpio.rules << EOF
SUBSYSTEM=="bcm2835-gpiomem", KERNEL=="gpiomem", GROUP="gpio", MODE="0660"
SUBSYSTEM=="gpio", KERNEL=="gpiochip*", ACTION=="add", GROUP="gpio", MODE="0660"
EOF

# Create gpio group if it doesn't exist
if ! getent group gpio >/dev/null; then
    groupadd -f gpio
fi

# Make sure our user is in the gpio group
usermod -aG gpio ${SERVICE_USER}

# Apply the new udev rules  
udevadm control --reload-rules
udevadm trigger
print_status "GPIO permissions configured for Pi 5"

# Set up PolicyKit permissions for ModemManager
print_status "Setting up PolicyKit permissions for ModemManager..."

# Create PolicyKit rule for ModemManager access
cat > /etc/polkit-1/localauthority/50-local.d/modemmanager.pkla << EOF
[Allow ModemManager for proscout user]
Identity=unix-user:${SERVICE_USER}
Action=org.freedesktop.ModemManager1.*
ResultAny=yes
ResultInactive=yes
ResultActive=yes

[Allow ModemManager Device Control for proscout user]
Identity=unix-user:${SERVICE_USER}
Action=org.freedesktop.ModemManager1.Device.Control
ResultAny=yes
ResultInactive=yes
ResultActive=yes

[Allow ModemManager Location Services for proscout user]
Identity=unix-user:${SERVICE_USER}
Action=org.freedesktop.ModemManager1.Location.*
ResultAny=yes
ResultInactive=yes
ResultActive=yes
EOF

# Set correct permissions for PolicyKit file
chmod 644 /etc/polkit-1/localauthority/50-local.d/modemmanager.pkla
print_status "PolicyKit permissions configured for ModemManager"

# Create additional udev rules for modem access
print_status "Setting up udev rules for modem access..."
cat > /etc/udev/rules.d/99-modem-permissions.rules << EOF
# Give dialout group access to modem devices
SUBSYSTEM=="tty", ATTRS{idVendor}=="1e0e", GROUP="dialout", MODE="0664"
SUBSYSTEM=="usb", ATTRS{idVendor}=="1e0e", GROUP="dialout", MODE="0664"

# Additional modem vendor IDs (add as needed)
SUBSYSTEM=="tty", ATTRS{idVendor}=="12d1", GROUP="dialout", MODE="0664"  # Huawei
SUBSYSTEM=="usb", ATTRS{idVendor}=="12d1", GROUP="dialout", MODE="0664"

# Generic USB serial devices
KERNEL=="ttyUSB*", GROUP="dialout", MODE="0664"
KERNEL=="ttyACM*", GROUP="dialout", MODE="0664"
EOF

# Set up camera permissions
print_status "Setting up camera permissions..."
cat > /etc/udev/rules.d/99-camera-permissions.rules << EOF
# Camera device permissions
SUBSYSTEM=="video4linux", GROUP="video", MODE="0664"
KERNEL=="video*", GROUP="video", MODE="0664"
EOF

# Apply udev rules
udevadm control --reload-rules
udevadm trigger
print_status "Device permissions configured"

# Configure Raspberry Pi settings for modem support
print_status "Configuring Raspberry Pi settings for cellular modem..."

# Ask user if they want to configure hardware interfaces interactively
read -p "Do you want to configure hardware interfaces interactively using raspi-config? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_status "Opening raspi-config for interactive configuration..."
    print_status "Please enable the following interfaces:"
    print_status "  - Serial Port: Enable hardware, disable console"
    print_status "  - SPI: Enable"
    print_status "  - I2C: Enable"
    print_status "  - Camera: Enable (if using camera)"
    raspi-config
    print_status "Interactive configuration completed"
else
    print_status "Using automatic hardware interface configuration..."
    # Enable serial hardware but disable serial console (required for USB modems)
    raspi-config nonint do_serial 2
    # Enable SPI (sometimes needed for modem communication)
    raspi-config nonint do_spi 0
    # Enable I2C (sometimes needed)
    raspi-config nonint do_i2c 0
    # Optionally enable camera
    read -p "Enable camera interface? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        raspi-config nonint do_camera 0
        print_status "Camera interface enabled"
    fi
fi
print_status "Raspberry Pi hardware interfaces configured"

# Set gpiozero to use lgpio backend for Pi 5
print_status "Configuring GPIO backend for Pi 5..."
cat >> "${USER_HOME}/.bashrc" << EOF
# Pi 5 GPIO Configuration
export GPIOZERO_PIN_FACTORY=lgpio
EOF

# Create directories
print_status "Creating directories..."
mkdir -p "${INSTALL_DIR}"
mkdir -p "${DEVICE_DIR}"
mkdir -p "${LOGS_DIR}"
mkdir -p "${SCRIPTS_DIR}"
chown -R ${SERVICE_USER}:${SERVICE_USER} "${INSTALL_DIR}"

# Copy Python files
print_status "Copying Python files..."
for file in *.py; do
    if [ -f "$file" ]; then
        cp "$file" "${DEVICE_DIR}/"
        chmod +x "${DEVICE_DIR}/$file"
        print_status "Copied $file"
    fi
done

# Copy config files if they exist
if [ -f "config.ini" ]; then
    cp "config.ini" "${DEVICE_DIR}/"
    print_status "Copied config.ini"
fi

# Create requirements file optimized for Pi 5
print_status "Creating Pi 5 optimized requirements.txt..."
cat > "${DEVICE_DIR}/requirements.txt" << EOF
opencv-python
exifread
tqdm
numpy
gpiozero
lgpio
readchar
requests
pyserial
pynmea2
dbus-python
EOF
chown ${SERVICE_USER}:${SERVICE_USER} "${DEVICE_DIR}/requirements.txt"
print_status "Created Pi 5 optimized requirements.txt"

# Create virtual environment
print_status "Creating virtual environment..."
sudo -u ${SERVICE_USER} python3 -m venv "${VENV_DIR}"

# Install dependencies
print_status "Installing Python dependencies..."
sudo -u ${SERVICE_USER} "${VENV_DIR}/bin/pip" install --upgrade pip
sudo -u ${SERVICE_USER} "${VENV_DIR}/bin/pip" install -r "${DEVICE_DIR}/requirements.txt"

# Generate device UUID
if [ ! -f "${DEVICE_DIR}/device_id.txt" ]; then
    print_status "Generating device UUID..."
    uuidgen > "${DEVICE_DIR}/device_id.txt"
    chmod 600 "${DEVICE_DIR}/device_id.txt"
    chown ${SERVICE_USER}:${SERVICE_USER} "${DEVICE_DIR}/device_id.txt"
    print_status "Generated UUID: $(cat ${DEVICE_DIR}/device_id.txt)"
fi

# Setup cellular modem configuration
print_status "Setting up cellular modem configuration..."

# Add USB power management fix to prevent connection drops
print_status "Configuring USB power management for cellular modem..."
cat > /etc/udev/rules.d/99-usb-no-suspend.rules << EOF
# Disable USB power management for SIM7600 cellular modems to prevent connection drops
SUBSYSTEM=="usb", ATTRS{idVendor}=="1e0e", ATTRS{idProduct}=="9001", ATTR{power/autosuspend}="-1"
EOF

# Create cellular modem setup script
cat > "${SCRIPTS_DIR}/setup_cellular.sh" << 'EOF'
#!/bin/bash

# Cellular modem setup script
print_status() {
    echo -e "\033[0;32m[INFO]\033[0m $1"
}

print_warning() {
    echo -e "\033[1;33m[WARN]\033[0m $1"
}

print_error() {
    echo -e "\033[0;31m[ERROR]\033[0m $1"
}

setup_cellular_connection() {
    local apn="$1"
    local connection_name="cellular"
    
    print_status "Setting up cellular connection with APN: $apn"
    
    # Check if modem is detected
    if ! mmcli -L | grep -q "modem"; then
        print_error "No modem detected by ModemManager"
        print_error "Available USB devices:"
        lsusb | grep -i sim || echo "No SIM modem found"
        return 1
    fi
    
    # Check if connection already exists
    if nmcli connection show | grep -q "$connection_name"; then
        print_warning "Connection '$connection_name' already exists, removing..."
        nmcli connection delete "$connection_name"
    fi
    
    # Create new cellular connection
    print_status "Creating cellular connection..."
    if nmcli connection add type gsm ifname cdc-wdm0 con-name "$connection_name" apn "$apn"; then
        print_status "Cellular connection created successfully"
        
        # Set auto-connect and priority
        nmcli connection modify "$connection_name" connection.autoconnect yes
        nmcli connection modify "$connection_name" connection.autoconnect-priority 100
        nmcli connection modify "$connection_name" connection.autoconnect-retries 0
        nmcli connection modify "$connection_name" ipv4.dhcp-timeout 60
        
        # Try to bring up the connection
        print_status "Activating cellular connection..."
        if nmcli connection up "$connection_name"; then
            print_status "Cellular connection activated successfully"
            
            # Wait a moment for IP assignment
            sleep 5
            
            # Test connectivity
            print_status "Testing connectivity..."
            if ping -c 3 8.8.8.8 >/dev/null 2>&1; then
                print_status "Cellular internet connection working!"
                return 0
            else
                print_warning "Connection established but internet test failed"
                print_warning "This might be normal if data plan is not active"
                return 0
            fi
        else
            print_error "Failed to activate cellular connection"
            return 1
        fi
    else
        print_error "Failed to create cellular connection"
        return 1
    fi
}

# Default APN (can be overridden)
APN="${1:-net.hotm}"

print_status "Starting cellular modem setup..."
print_status "Using APN: $APN"

# Wait for modem to be ready
print_status "Waiting for modem to be detected..."
for i in {1..30}; do
    if mmcli -L | grep -q "modem"; then
        print_status "Modem detected!"
        break
    fi
    if [ $i -eq 30 ]; then
        print_error "Timeout waiting for modem detection"
        exit 1
    fi
    sleep 2
done

# Check modem status
print_status "Checking modem status..."
mmcli -m 0

# Setup cellular connection
setup_cellular_connection "$APN"

print_status "Cellular setup complete!"
EOF

chmod +x "${SCRIPTS_DIR}/setup_cellular.sh"
chown ${SERVICE_USER}:${SERVICE_USER} "${SCRIPTS_DIR}/setup_cellular.sh"

# Create cellular connection monitoring script
print_status "Creating cellular connection monitoring script..."
cat > "${SCRIPTS_DIR}/monitor_cellular.sh" << 'EOF'
#!/bin/bash

# Cellular connection monitoring and auto-recovery script

LOG_FILE="/var/log/cellular_monitor.log"

log_message() {
    echo "$(date): $1" >> "$LOG_FILE"
}

check_connectivity() {
    # Test internet connectivity
    if ping -c 2 8.8.8.8 >/dev/null 2>&1; then
        return 0  # Connected
    else
        return 1  # Not connected
    fi
}

cleanup_bearers() {
    log_message "Cleaning up duplicate bearers..."
    # Get list of bearers and remove disconnected ones
    mmcli -m 0 2>/dev/null | grep -o "/org/freedesktop/ModemManager1/Bearer/[0-9]*" | while read bearer_path; do
        bearer_num=$(echo "$bearer_path" | grep -o "[0-9]*$")
        
        # Check if bearer is connected
        if ! mmcli -b "$bearer_num" 2>/dev/null | grep -q "connected: yes"; then
            log_message "Removing disconnected bearer $bearer_num"
            mmcli -m 0 --delete-bearer="$bearer_num" 2>/dev/null
        fi
    done
}

# Check signal quality and reconnect if too weak
check_signal_quality() {
    signal=$(mmcli -m 0 2>/dev/null | grep "signal quality" | awk '{print $4}' | sed 's/%//')
    if [ -n "$signal" ] && [ "$signal" -lt 15 ]; then
        log_message "Signal quality too low ($signal%), attempting reconnection"
        return 1
    fi
    return 0
}

# Main monitoring logic
if ! check_connectivity || ! check_signal_quality; then
    log_message "Cellular connectivity issue detected, attempting recovery..."
    
    # Clean up broken bearers
    cleanup_bearers
    
    # Try to reconnect
    nmcli connection down cellular 2>/dev/null
    sleep 5
    nmcli connection up cellular 2>/dev/null
    
    sleep 10
    if check_connectivity; then
        log_message "Cellular connection restored successfully"
    else
        log_message "Failed to restore cellular connection"
    fi
fi
EOF

chmod +x "${SCRIPTS_DIR}/monitor_cellular.sh"
chown ${SERVICE_USER}:${SERVICE_USER} "${SCRIPTS_DIR}/monitor_cellular.sh"

# Create log file for monitoring
touch /var/log/cellular_monitor.log
chmod 644 /var/log/cellular_monitor.log

# Create the ProScout startup script with USB device checking and cellular setup
print_status "Creating ProScout startup script with device verification and cellular setup..."
cat > "${DEVICE_DIR}/proscout_startup.sh" << 'EOF'
#!/bin/bash

# Function to check if required USB modem devices are present
check_usb_modem_devices() {
    echo "=== Checking for required USB modem devices ==="
    
    # Check for ttyUSB2 (GPS/Modem device - common for SIM7600X)
    if [ ! -e "/dev/ttyUSB2" ]; then
        echo "WARNING: /dev/ttyUSB2 not found!"
        echo "Available ttyUSB devices:"
        ls -la /dev/ttyUSB* 2>/dev/null || echo "No ttyUSB devices found"
        echo "USB devices:"
        lsusb | grep -i sim || echo "No SIM modem found"
        echo "Continuing without GPS/Modem device..."
        return 1
    else
        echo "Found /dev/ttyUSB2 - GPS/Modem device ready"
        return 0
    fi
}

setup_cellular_if_needed() {
    echo "=== Checking cellular connectivity ==="
    
    # Check if cellular connection exists and is active
    if nmcli connection show --active | grep -q "gsm"; then
        echo "Cellular connection already active"
        return 0
    fi
    
    # Check if cellular connection exists but is inactive
    if nmcli connection show | grep -q "cellular"; then
        echo "Cellular connection exists, trying to activate..."
        if nmcli connection up cellular; then
            echo "Cellular connection activated successfully"
            return 0
        else
            echo "Failed to activate existing cellular connection"
        fi
    fi
    
    # If no cellular connection, try to set it up
    echo "No active cellular connection found, attempting setup..."
    if [ -x "/home/proscout/ProScout-master/scripts/setup_cellular.sh" ]; then
        /home/proscout/ProScout-master/scripts/setup_cellular.sh
    else
        echo "Cellular setup script not found, skipping automatic setup"
    fi
}

initialize_gps() {
    echo "=== GPS initialization ==="
    
    # Check if device exists first
    if ! check_usb_modem_devices; then
        echo "Skipping GPS initialization - USB modem device not found"
        return 1
    fi
    
    echo "systemctl stop ModemManager"
    sudo systemctl stop ModemManager
    sleep 5

    sudo stty -F /dev/ttyUSB2 115200 raw -echo -cstopb 2>/dev/null
    printf "AT+CGNSPWR=0\r\n" | sudo tee /dev/ttyUSB2 >/dev/null 2>&1
    sleep 2
    printf "AT+CGNSPWR=1\r\n" | sudo tee /dev/ttyUSB2 >/dev/null 2>&1
    sleep 3
    printf "AT+CGNSTST=1\r\n" | sudo tee /dev/ttyUSB2 >/dev/null 2>&1
    sleep 3
    echo "systemctl start ModemManager"
    sudo systemctl start ModemManager
    sleep 30

    # Check if modem is detected
    if sudo mmcli -L | grep -q "No modems were found"; then
        echo "No modems detected by ModemManager"
        return 1
    fi

    mmcli -m 0 --location-enable-gps-nmea
    mmcli -m 0 --location-enable-gps-raw
    mmcli -m 0 --location-set-gps-refresh-rate=2
    echo "Verifying GPS status..."
    gps_status=$(sudo mmcli -m 0 --location-status)
    echo "GPS Status: $gps_status"
        
    if echo "$gps_status" | grep -q "gps-nmea" && echo "$gps_status" | grep -q "gps-raw"; then
        echo "GPS verification: SUCCESS"
        
        # Try to get initial GPS data
        echo "Testing GPS data retrieval..."
        sudo mmcli -m 0 --location-get | head -20
        
        return 0
    else
        echo "GPS verification: FAILED"
        echo "Current GPS status:"
        sudo mmcli -m 0 --location-status
        return 1
    fi
}

# Wait for system to be ready
echo "Waiting for system initialization..."
sleep 10

# Check devices and initialize GPS
check_usb_modem_devices
device_check_result=$?

if [ $device_check_result -eq 0 ]; then
    # Setup cellular connectivity first
    setup_cellular_if_needed
    
    # Then initialize GPS
    initialize_gps
    gps_status=$?
    if [ $gps_status -eq 0 ]; then
        echo "GPS initialization completed successfully"
    else
        echo "GPS initialization failed, but continuing with main application"
    fi
else
    echo "Required USB modem devices not found, continuing without GPS"
fi

# Activate virtual environment
echo "Activating Python virtual environment..."
source /home/proscout/ProScout-master/ProScout-Device/bin/activate

# Change to the device-manager directory where config.ini is located
cd /home/proscout/ProScout-master/device-manager

# Run your Python script
echo "Starting ProScout main application..."
python3 main.py
EOF

chmod +x "${DEVICE_DIR}/proscout_startup.sh"
chown ${SERVICE_USER}:${SERVICE_USER} "${DEVICE_DIR}/proscout_startup.sh"
print_status "Created proscout_startup.sh with device checking and cellular setup"

# Create systemd service file optimized for Pi 5
print_status "Creating systemd service optimized for Pi 5..."
cat > "/etc/systemd/system/${SOFTWARE_NAME}.service" << EOF
[Unit]
Description=ProScout Device Management Software
After=network-online.target NetworkManager.service ModemManager.service
Wants=network-online.target NetworkManager.service ModemManager.service

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${DEVICE_DIR}
Environment="PYTHONPATH=${DEVICE_DIR}"
Environment="GPIOZERO_PIN_FACTORY=lgpio"
ExecStart=/bin/bash ${DEVICE_DIR}/proscout_startup.sh
Restart=always
RestartSec=30
StandardOutput=append:${LOGS_DIR}/device-manager.log
StandardError=append:${LOGS_DIR}/device-manager.error.log

[Install]
WantedBy=multi-user.target
EOF

# Create log files
touch "${LOGS_DIR}/device-manager.log"
touch "${LOGS_DIR}/device-manager.error.log"
chown ${SERVICE_USER}:${SERVICE_USER} "${LOGS_DIR}/device-manager.log"
chown ${SERVICE_USER}:${SERVICE_USER} "${LOGS_DIR}/device-manager.error.log"

# Create management script
print_status "Creating management script..."
cat > "${SCRIPTS_DIR}/manage.sh" << EOF
#!/bin/bash

SERVICE_NAME="${SOFTWARE_NAME}"
LOGS_DIR="${LOGS_DIR}"

case "\$1" in
    start)
        sudo systemctl start \$SERVICE_NAME
        echo "Service started"
        ;;
    stop)
        sudo systemctl stop \$SERVICE_NAME
        echo "Service stopped"
        ;;
    restart)
        sudo systemctl restart \$SERVICE_NAME
        echo "Service restarted"
        ;;
    status)
        sudo systemctl status \$SERVICE_NAME
        ;;
    logs)
        tail -f \$LOGS_DIR/device-manager.log
        ;;
    errors)
        tail -f \$LOGS_DIR/device-manager.error.log
        ;;
    check-devices)
        echo "Checking USB modem devices:"
        ls -la /dev/ttyUSB* 2>/dev/null || echo "No ttyUSB devices found"
        echo ""
        echo "USB devices:"
        lsusb | grep -i sim || echo "No SIM modem detected"
        echo ""
        echo "ModemManager status:"
        sudo mmcli -L
        echo ""
        echo "Cellular connections:"
        nmcli connection show
        echo ""
        echo "Active connections:"
        nmcli device status
        ;;
    check-permissions)
        echo "Checking user permissions:"
        echo "Groups for ${SERVICE_USER}:"
        groups ${SERVICE_USER}
        echo ""
        echo "PolicyKit rules:"
        ls -la /etc/polkit-1/localauthority/50-local.d/modemmanager.pkla 2>/dev/null || echo "PolicyKit rules not found"
        echo ""
        echo "Device permissions:"
        ls -la /dev/ttyUSB* 2>/dev/null || echo "No ttyUSB devices found"
        ls -la /dev/video* 2>/dev/null || echo "No video devices found"
        echo ""
        echo "Udev rules:"
        ls -la /etc/udev/rules.d/99-*permissions.rules 2>/dev/null || echo "No custom permission rules found"
        ;;
    setup-cellular)
        APN="\${2:-net.hotm}"
        echo "Setting up cellular with APN: \$APN"
        /home/proscout/ProScout-master/scripts/setup_cellular.sh "\$APN"
        ;;
    test-cellular)
        echo "Testing cellular connectivity:"
        ping -c 4 8.8.8.8
        ;;
    monitor-cellular)
        echo "Running cellular connection monitor:"
        /home/proscout/ProScout-master/scripts/monitor_cellular.sh
        ;;
    cleanup-bearers)
        echo "Cleaning up duplicate bearers:"
        mmcli -m 0 2>/dev/null | grep -o "/org/freedesktop/ModemManager1/Bearer/[0-9]*" | while read bearer_path; do
            bearer_num=\$(echo "\$bearer_path" | grep -o "[0-9]*\$")