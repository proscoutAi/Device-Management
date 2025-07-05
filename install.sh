#!/bin/bash

# Complete installation script for Device Management software
# For Raspberry Pi 5 - Updated with Pi 5 optimizations and cellular modem setup
# FIXED VERSION - Corrected modem detection logic and improved error handling

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

# Get APN configuration from user
print_status "Cellular Modem Configuration"
echo "=============================="
echo
echo "Please configure your cellular modem settings:"
echo "The APN (Access Point Name) is provided by your cellular carrier."
echo "Common APNs:"
echo "  - net.hotm (Hologram)"
echo "  - iot.1nce.net (1NCE)"
echo "  - internet (Generic/T-Mobile)"
echo "  - broadband (Verizon)"
echo "  - fast.t-mobile.com (T-Mobile)"
echo
read -p "Enter your APN [default: net.hotm]: " USER_APN
USER_APN=${USER_APN:-net.hotm}
print_status "Using APN: ${USER_APN}"
echo

# Ask if user wants to set up cellular connection now or later
echo "When would you like to configure the cellular connection?"
echo "1. Now (during installation)"
echo "2. Later (manually after installation)"
echo
read -p "Select option (1-2) [default: 1]: " CELLULAR_SETUP_OPTION
CELLULAR_SETUP_OPTION=${CELLULAR_SETUP_OPTION:-1}

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

# Update package lists first
print_status "Updating package lists..."
apt update

# Install essential build dependencies first
print_status "Installing build dependencies..."
apt install -y build-essential pkg-config cmake

# Install D-Bus development libraries (CRITICAL FIX)
print_status "Installing D-Bus development libraries..."
apt install -y libdbus-1-dev libdbus-glib-1-dev dbus python3-dbus

# Install system dependencies - Pi 5 optimized with additional modem support
print_status "Installing system dependencies for Pi 5..."
apt install -y python3-pip python3-venv python3-dev python3-opencv git curl unzip uuid-runtime \
    python3-gpiozero python3-lgpio lgpio python3-libgpiod gpiod i2c-tools \
    libqmi-utils libmbim-utils policykit-1 python3-gi python3-gi-dev \
    usb-modeswitch usb-modeswitch-data minicom

# Install ModemManager and NetworkManager with proper dependencies
print_status "Installing cellular modem support..."
apt install -y modemmanager modemmanager-dev libmm-glib-dev network-manager \
    gpsd gpsd-clients libgps-dev screen

# Install additional USB and serial support
print_status "Installing USB and serial support..."
apt install -y setserial usbutils

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

# Create comprehensive udev rules for modem access
print_status "Setting up comprehensive udev rules for modem access..."
cat > /etc/udev/rules.d/99-modem-permissions.rules << EOF
# SIM7600 series modems
SUBSYSTEM=="tty", ATTRS{idVendor}=="1e0e", ATTRS{idProduct}=="9001", GROUP="dialout", MODE="0664"
SUBSYSTEM=="usb", ATTRS{idVendor}=="1e0e", ATTRS{idProduct}=="9001", GROUP="dialout", MODE="0664"

# Additional SIM7600 variants
SUBSYSTEM=="tty", ATTRS{idVendor}=="1e0e", GROUP="dialout", MODE="0664"
SUBSYSTEM=="usb", ATTRS{idVendor}=="1e0e", GROUP="dialout", MODE="0664"

# Huawei modems
SUBSYSTEM=="tty", ATTRS{idVendor}=="12d1", GROUP="dialout", MODE="0664"
SUBSYSTEM=="usb", ATTRS{idVendor}=="12d1", GROUP="dialout", MODE="0664"

# Quectel modems
SUBSYSTEM=="tty", ATTRS{idVendor}=="2c7c", GROUP="dialout", MODE="0664"
SUBSYSTEM=="usb", ATTRS{idVendor}=="2c7c", GROUP="dialout", MODE="0664"

# Generic USB serial devices
KERNEL=="ttyUSB*", GROUP="dialout", MODE="0664"
KERNEL=="ttyACM*", GROUP="dialout", MODE="0664"
KERNEL=="cdc-wdm*", GROUP="dialout", MODE="0664"

# QMI and MBIM devices
SUBSYSTEM=="usbmisc", KERNEL=="cdc-wdm*", GROUP="dialout", MODE="0664"
SUBSYSTEM=="usb", ENV{ID_USB_INTERFACE_CLASS}=="02", ENV{ID_USB_INTERFACE_SUBCLASS}=="0d", GROUP="dialout", MODE="0664"
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

# Configure USB power management to prevent modem disconnection
print_status "Configuring USB power management..."
cat > /etc/udev/rules.d/99-usb-no-suspend.rules << EOF
# Disable USB power management for cellular modems to prevent connection drops
SUBSYSTEM=="usb", ATTRS{idVendor}=="1e0e", ATTR{power/autosuspend}="-1"
SUBSYSTEM=="usb", ATTRS{idVendor}=="12d1", ATTR{power/autosuspend}="-1"
SUBSYSTEM=="usb", ATTRS{idVendor}=="2c7c", ATTR{power/autosuspend}="-1"

# Disable autosuspend for all USB serial devices
ACTION=="add", SUBSYSTEM=="usb", DRIVERS=="usb", ATTR{power/autosuspend}="-1"
EOF

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

# Ensure services are enabled and started
print_status "Configuring system services..."
systemctl enable ModemManager
systemctl enable NetworkManager
systemctl start ModemManager
systemctl start NetworkManager

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

# Create or update config.ini with APN setting
print_status "Configuring APN in config file..."
if [ -f "${DEVICE_DIR}/config.ini" ]; then
    # Update existing config.ini with APN
    if grep -q "\[cellular\]" "${DEVICE_DIR}/config.ini"; then
        # Update existing cellular section
        sed -i "/\[cellular\]/,/\[.*\]/ s/^apn=.*/apn=${USER_APN}/" "${DEVICE_DIR}/config.ini"
        if ! grep -q "^apn=" "${DEVICE_DIR}/config.ini"; then
            # Add APN line if it doesn't exist
            sed -i "/\[cellular\]/a apn=${USER_APN}" "${DEVICE_DIR}/config.ini"
        fi
    else
        # Add cellular section
        echo "" >> "${DEVICE_DIR}/config.ini"
        echo "[cellular]" >> "${DEVICE_DIR}/config.ini"
        echo "apn=${USER_APN}" >> "${DEVICE_DIR}/config.ini"
    fi
else
    # Create new config.ini with APN
    cat > "${DEVICE_DIR}/config.ini" << EOF
[cellular]
apn=${USER_APN}
EOF
fi
chown ${SERVICE_USER}:${SERVICE_USER} "${DEVICE_DIR}/config.ini"
print_status "APN configured: ${USER_APN}"

# Create requirements file optimized for Pi 5 with fixed dbus-python
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
# Use system dbus-python instead of pip version
# dbus-python will be handled by system package
EOF
chown ${SERVICE_USER}:${SERVICE_USER} "${DEVICE_DIR}/requirements.txt"
print_status "Created Pi 5 optimized requirements.txt"

# Create virtual environment
print_status "Creating virtual environment..."
sudo -u ${SERVICE_USER} python3 -m venv "${VENV_DIR}" --system-site-packages

# Install dependencies
print_status "Installing Python dependencies..."
sudo -u ${SERVICE_USER} "${VENV_DIR}/bin/pip" install --upgrade pip
sudo -u ${SERVICE_USER} "${VENV_DIR}/bin/pip" install -r "${DEVICE_DIR}/requirements.txt"

# Verify dbus-python is available
print_status "Verifying dbus-python availability..."
if sudo -u ${SERVICE_USER} "${VENV_DIR}/bin/python" -c "import dbus; print('dbus-python is available')" 2>/dev/null; then
    print_status "dbus-python is available via system packages"
else
    print_warning "dbus-python not available, trying alternative installation..."
    # Try installing via system package manager in virtual environment
    sudo -u ${SERVICE_USER} "${VENV_DIR}/bin/pip" install --force-reinstall --no-deps dbus-python==1.3.2
fi

# Generate device UUID
if [ ! -f "${DEVICE_DIR}/device_id.txt" ]; then
    print_status "Generating device UUID..."
    
    # Use Python UUID generation as primary method (most reliable)
    if command -v python3 >/dev/null 2>&1; then
        DEVICE_UUID=$(python3 -c "import uuid; print(uuid.uuid4())")
        echo "${DEVICE_UUID}" > "${DEVICE_DIR}/device_id.txt"
        print_status "Generated UUID (Python): ${DEVICE_UUID}"
    elif command -v uuidgen >/dev/null 2>&1; then
        # Fallback to uuidgen if Python is not available
        DEVICE_UUID=$(uuidgen)
        echo "${DEVICE_UUID}" > "${DEVICE_DIR}/device_id.txt"
        print_status "Generated UUID (uuidgen): ${DEVICE_UUID}"
    else
        # Final fallback method
        DEVICE_UUID=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || date +%s%N | sha256sum | cut -c1-32)
        echo "${DEVICE_UUID}" > "${DEVICE_DIR}/device_id.txt"
        print_status "Generated UUID (fallback): ${DEVICE_UUID}"
    fi
    
    # Set permissions
    chmod 600 "${DEVICE_DIR}/device_id.txt"
    chown ${SERVICE_USER}:${SERVICE_USER} "${DEVICE_DIR}/device_id.txt"
    
    # Verify the file was created correctly
    if [ -s "${DEVICE_DIR}/device_id.txt" ]; then
        print_status "Device ID file created successfully: $(cat ${DEVICE_DIR}/device_id.txt)"
    else
        print_error "Failed to create device ID file!"
        # Try one more time with a simple method
        date +%s%N | sha256sum | cut -c1-32 > "${DEVICE_DIR}/device_id.txt"
        chown ${SERVICE_USER}:${SERVICE_USER} "${DEVICE_DIR}/device_id.txt"
        print_warning "Created fallback device ID: $(cat ${DEVICE_DIR}/device_id.txt)"
    fi
else
    print_status "Device UUID already exists: $(cat ${DEVICE_DIR}/device_id.txt)"
fi

# Create FIXED modem detection and initialization script
print_status "Creating FIXED modem detection script..."
cat > "${SCRIPTS_DIR}/detect_modem.sh" << 'EOF'
#!/bin/bash

print_status() {
    echo -e "\033[0;32m[INFO]\033[0m $1"
}

print_warning() {
    echo -e "\033[1;33m[WARN]\033[0m $1"
}

print_error() {
    echo -e "\033[0;31m[ERROR]\033[0m $1"
}

# Function to detect and switch USB modems
detect_and_switch_modem() {
    print_status "Detecting USB modems..."
    
    # Check for common modem vendor IDs
    local sim7600_detected=false
    local huawei_detected=false
    local quectel_detected=false
    
    # SIM7600 series detection
    if lsusb | grep -q "1e0e"; then
        print_status "SIM7600 series modem detected"
        sim7600_detected=true
    fi
    
    # Huawei modem detection
    if lsusb | grep -q "12d1"; then
        print_status "Huawei modem detected"
        huawei_detected=true
    fi
    
    # Quectel modem detection
    if lsusb | grep -q "2c7c"; then
        print_status "Quectel modem detected"
        quectel_detected=true
    fi
    
    # If no known modems detected, show all USB devices
    if ! $sim7600_detected && ! $huawei_detected && ! $quectel_detected; then
        print_warning "No known cellular modems detected"
        print_status "All USB devices:"
        lsusb
        return 1
    fi
    
    # Wait for USB mode switching to complete
    print_status "Waiting for USB mode switching..."
    sleep 10
    
    # Run usb_modeswitch if needed
    if command -v usb_modeswitch >/dev/null 2>&1; then
        print_status "Running USB mode switch..."
        usb_modeswitch -v 1e0e -p 9001 -V 1e0e -P 9001 -J 2>/dev/null || true
        sleep 5
    fi
    
    # Check for serial devices
    print_status "Checking for serial devices..."
    if ls /dev/ttyUSB* >/dev/null 2>&1; then
        print_status "Found serial devices:"
        ls -la /dev/ttyUSB*
    else
        print_warning "No ttyUSB devices found"
    fi
    
    if ls /dev/ttyACM* >/dev/null 2>&1; then
        print_status "Found ACM devices:"
        ls -la /dev/ttyACM*
    fi
    
    # Check for QMI/MBIM devices
    if ls /dev/cdc-wdm* >/dev/null 2>&1; then
        print_status "Found QMI/MBIM devices:"
        ls -la /dev/cdc-wdm*
    fi
    
    return 0
}

# FIXED: Function to wait for ModemManager to detect modem
wait_for_modem_detection() {
    print_status "Waiting for ModemManager to detect modem..."
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        local modem_output=$(mmcli -L 2>/dev/null)
        
        # FIXED: Multiple detection methods with better patterns
        if echo "$modem_output" | grep -q "/Modem/"; then
            print_status "Modem detected by ModemManager (path method)!"
            echo "$modem_output"
            return 0
        fi
        
        if echo "$modem_output" | grep -q "SIMCOM_SIM7600"; then
            print_status "SIM7600 modem detected by ModemManager (name method)!"
            echo "$modem_output"
            return 0
        fi
        
        if echo "$modem_output" | grep -q "org/freedesktop/ModemManager1/Modem"; then
            print_status "Modem detected by ModemManager (full path method)!"
            echo "$modem_output"
            return 0
        fi
        
        # FIXED: Also check for any line that doesn't say "No modems were found"
        if [ -n "$modem_output" ] && ! echo "$modem_output" | grep -q "No modems were found"; then
            print_status "Modem detected by ModemManager (general method)!"
            echo "$modem_output"
            return 0
        fi
        
        attempt=$((attempt + 1))
        print_status "Attempt $attempt/$max_attempts - waiting..."
        sleep 2
    done
    
    print_error "Timeout waiting for modem detection"
    print_status "Final ModemManager output:"
    mmcli -L 2>/dev/null || print_error "ModemManager not responding"
    return 1
}

# Function to initialize modem
initialize_modem() {
    print_status "Initializing modem..."
    
    # Get modem number (usually 0 for first modem)
    local modem_num=0
    
    # Check modem status
    if mmcli -m $modem_num --simple-status 2>/dev/null; then
        print_status "Modem status retrieved successfully"
    else
        print_warning "Could not retrieve modem status"
    fi
    
    # Enable modem if disabled
    if mmcli -m $modem_num 2>/dev/null | grep -q "state.*disabled"; then
        print_status "Enabling modem..."
        mmcli -m $modem_num --enable
        sleep 5
    fi
    
    return 0
}

# Main detection flow
main() {
    print_status "Starting modem detection and initialization..."
    
    # Check if ModemManager is running
    if ! systemctl is-active --quiet ModemManager; then
        print_status "Starting ModemManager..."
        systemctl start ModemManager
        sleep 5
    fi
    
    # FIXED: Quick check if modem is already detected
    if mmcli -L 2>/dev/null | grep -q "/Modem/"; then
        print_status "Modem already detected by ModemManager!"
        mmcli -L
        initialize_modem
        print_status "Modem detection and initialization complete!"
        return 0
    fi
    
    # Only restart ModemManager if modem not already detected
    print_status "Restarting ModemManager for clean detection..."
    systemctl restart ModemManager
    sleep 10
    
    # Detect and switch modem
    if detect_and_switch_modem; then
        print_status "Modem detection successful"
    else
        print_error "Modem detection failed"
        exit 1
    fi
    
    # Wait for ModemManager detection
    if wait_for_modem_detection; then
        print_status "ModemManager detection successful"
    else
        print_error "ModemManager detection failed"
        exit 1
    fi
    
    # Initialize modem
    if initialize_modem; then
        print_status "Modem initialization successful"
    else
        print_warning "Modem initialization had issues but continuing..."
    fi
    
    print_status "Modem detection and initialization complete!"
}

# Run main function
main "$@"
EOF

chmod +x "${SCRIPTS_DIR}/detect_modem.sh"
chown ${SERVICE_USER}:${SERVICE_USER} "${SCRIPTS_DIR}/detect_modem.sh"

# Create enhanced cellular setup script
cat > "${SCRIPTS_DIR}/setup_cellular.sh" << EOF
#!/bin/bash

# Enhanced cellular modem setup script with better error handling and FIXED detection

print_status() {
    echo -e "\033[0;32m[INFO]\033[0m \$1"
}

print_warning() {
    echo -e "\033[1;33m[WARN]\033[0m \$1"
}

print_error() {
    echo -e "\033[0;31m[ERROR]\033[0m \$1"
}

setup_cellular_connection() {
    local apn="\$1"
    local connection_name="cellular"
    
    print_status "Setting up cellular connection with APN: \$apn"
    
    # FIXED: Better modem detection check
    print_status "Checking modem status..."
    local modem_output=\$(mmcli -L 2>/dev/null)
    
    if ! echo "\$modem_output" | grep -q "/Modem/"; then
        print_warning "No modem detected by ModemManager, attempting detection..."
        
        # Try running detection script
        if [ -x "${SCRIPTS_DIR}/detect_modem.sh" ]; then
            if ! ${SCRIPTS_DIR}/detect_modem.sh; then
                print_error "Modem detection failed"
                return 1
            fi
        else
            print_error "Modem detection script not found"
            return 1
        fi
        
        # Check again after detection
        modem_output=\$(mmcli -L 2>/dev/null)
        if ! echo "\$modem_output" | grep -q "/Modem/"; then
            print_error "Still no modem detected after running detection script"
            print_error "Debug information:"
            print_error "USB devices:"
            lsusb
            print_error "Serial devices:"
            ls -la /dev/ttyUSB* /dev/ttyACM* /dev/cdc-wdm* 2>/dev/null || echo "No serial devices found"
            return 1
        fi
    fi
    
    # Get modem path
    local modem_path=\$(echo "\$modem_output" | grep -o '/org/freedesktop/ModemManager1/Modem/[0-9]*' | head -1)
    local modem_num=\$(echo "\$modem_path" | grep -o '[0-9]*\$')
    
    print_status "Using modem: \$modem_path (modem \$modem_num)"
    
    # Check if connection already exists
    if nmcli connection show | grep -q "\$connection_name"; then
        print_warning "Connection '\$connection_name' already exists, removing..."
        nmcli connection delete "\$connection_name"
    fi
    
    # Create new cellular connection
    print_status "Creating cellular connection..."
    if nmcli connection add type gsm ifname cdc-wdm0 con-name "\$connection_name" apn "\$apn"; then
        print_status "Cellular connection created successfully"
        
        # Set connection properties
        nmcli connection modify "\$connection_name" connection.autoconnect yes
        nmcli connection modify "\$connection_name" connection.autoconnect-priority 50
        nmcli connection modify "\$connection_name" connection.autoconnect-retries 0
        nmcli connection modify "\$connection_name" ipv4.dhcp-timeout 60
        nmcli connection modify "\$connection_name" gsm.auto-config yes
        
        # Try to bring up the connection
        print_status "Activating cellular connection..."
        if nmcli connection up "\$connection_name"; then
            print_status "Cellular connection activated successfully"
            
            # Wait for IP assignment
            sleep 10
            
            # Check connection status
            nmcli device status
            
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

# Use configured APN or override from command line
APN="\${1:-${USER_APN}}"

print_status "Starting cellular modem setup..."
print_status "Using APN: \$APN"

# Setup cellular connection
setup_cellular_connection "\$APN"

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
    echo "$(date): $1" | tee -a "$LOG_FILE"
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
log_message "Starting cellular connection check..."

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
else
    log_message "Cellular connection is healthy"
fi
EOF

chmod +x "${SCRIPTS_DIR}/monitor_cellular.sh"
chown ${SERVICE_USER}:${SERVICE_USER} "${SCRIPTS_DIR}/monitor_cellular.sh"

# Create log file for monitoring
touch /var/log/cellular_monitor.log
chmod 644 /var/log/cellular_monitor.log

# Create the ProScout startup script with FIXED modem detection
print_status "Creating ProScout startup script with FIXED modem detection..."
cat > "${DEVICE_DIR}/proscout_startup.sh" << EOF
#!/bin/bash

# Enhanced ProScout startup script with FIXED modem detection and error handling

# Set environment variables for Pi 5
export GPIOZERO_PIN_FACTORY=lgpio

# Logging function
log_message() {
    echo "\$(date): \$1" | tee -a /home/proscout/ProScout-master/logs/startup.log
}

# FIXED: Function to detect and initialize modem
initialize_modem_system() {
    log_message "=== Starting modem system initialization ==="
    
    # Quick check if modem is already detected
    if mmcli -L 2>/dev/null | grep -q "/Modem/"; then
        log_message "Modem already detected by ModemManager!"
        mmcli -L
        return 0
    fi
    
    # Run comprehensive modem detection
    log_message "Running modem detection script..."
    if ${SCRIPTS_DIR}/detect_modem.sh; then
        log_message "Modem detection completed successfully"
        return 0
    else
        log_message "Modem detection failed, but continuing..."
        return 1
    fi
}

setup_cellular_if_needed() {
    log_message "=== Checking cellular connectivity ==="
    
    # Check if cellular connection exists and is active
    if nmcli connection show --active | grep -q "gsm"; then
        log_message "Cellular connection already active"
        return 0
    fi
    
    # Check if cellular connection exists but is inactive
    if nmcli connection show | grep -q "cellular"; then
        log_message "Cellular connection exists, trying to activate..."
        if nmcli connection up cellular; then
            log_message "Cellular connection activated successfully"
            return 0
        else
            log_message "Failed to activate existing cellular connection"
        fi
    fi
    
    # If no cellular connection, try to set it up
    log_message "No active cellular connection found, attempting setup..."
    if [ -x "${SCRIPTS_DIR}/setup_cellular.sh" ]; then
        ${SCRIPTS_DIR}/setup_cellular.sh
    else
        log_message "Cellular setup script not found, skipping automatic setup"
    fi
}

initialize_gps() {
    log_message "=== GPS initialization ==="
    
    # FIXED: Check if ModemManager detected a modem
    if ! mmcli -L 2>/dev/null | grep -q "/Modem/"; then
        log_message "No modem detected by ModemManager, skipping GPS initialization"
        return 1
    fi
    
    # Check if GPS is already initialized
    if mmcli -m 0 --location-status 2>/dev/null | grep -q "gps-nmea.*enabled"; then
        log_message "GPS already initialized and enabled, skipping restart..."
        return 0
    fi
    
    log_message "Initializing GPS on modem..."
    
    # Enable GPS location services
    if mmcli -m 0 --location-enable-gps-nmea 2>/dev/null; then
        log_message "GPS NMEA enabled successfully"
    else
        log_message "Failed to enable GPS NMEA"
        return 1
    fi
    
    if mmcli -m 0 --location-enable-gps-raw 2>/dev/null; then
        log_message "GPS RAW enabled successfully"
    else
        log_message "Failed to enable GPS RAW"
    fi
    
    # Set GPS refresh rate
    if mmcli -m 0 --location-set-gps-refresh-rate=2 2>/dev/null; then
        log_message "GPS refresh rate set to 2 seconds"
    else
        log_message "Failed to set GPS refresh rate"
    fi
    
    # Verify GPS status
    log_message "Verifying GPS status..."
    gps_status=\$(mmcli -m 0 --location-status 2>/dev/null)
    log_message "GPS Status: \$gps_status"
    
    if echo "\$gps_status" | grep -q "gps-nmea.*enabled"; then
        log_message "GPS initialization: SUCCESS"
        return 0
    else
        log_message "GPS initialization: FAILED"
        return 1
    fi
}

# Main startup sequence
main() {
    log_message "=== ProScout Device Manager Startup ==="
    log_message "Starting initialization sequence..."
    
    # Wait for system to be ready
    log_message "Waiting for system initialization..."
    sleep 15
    
    # Initialize modem system
    initialize_modem_system
    modem_status=\$?
    
    if [ \$modem_status -eq 0 ]; then
        # Setup cellular connectivity
        setup_cellular_if_needed
        
        # Initialize GPS
        initialize_gps
        gps_status=\$?
        if [ \$gps_status -eq 0 ]; then
            log_message "GPS initialization completed successfully"
        else
            log_message "GPS initialization failed, but continuing with main application"
        fi
    else
        log_message "Modem system initialization failed, continuing without cellular features"
    fi
    
    # Activate virtual environment
    log_message "Activating Python virtual environment..."
    source /home/proscout/ProScout-master/ProScout-Device/bin/activate
    
    # Change to the device-manager directory
    cd /home/proscout/ProScout-master/device-manager
    
    # Run the main application
    log_message "Starting ProScout main application..."
    python3 main.py
    
    # If main.py exits, log the event and keep service alive
    log_message "Main application exited, keeping service alive..."
    while true; do
        log_message "Service running... (\$(date))"
        sleep 300  # Log every 5 minutes instead of every minute
    done
}

# Run main function
main "\$@"
EOF

chmod +x "${DEVICE_DIR}/proscout_startup.sh"
chown ${SERVICE_USER}:${SERVICE_USER} "${DEVICE_DIR}/proscout_startup.sh"
print_status "Created enhanced proscout_startup.sh with FIXED modem detection"

# Create systemd service file optimized for Pi 5
print_status "Creating systemd service optimized for Pi 5..."
cat > "/etc/systemd/system/${SOFTWARE_NAME}.service" << EOF
[Unit]
Description=ProScout Device Management Software
After=network-online.target NetworkManager.service ModemManager.service usb.target
Wants=network-online.target NetworkManager.service ModemManager.service
Requires=usb.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${DEVICE_DIR}
Environment="PYTHONPATH=${DEVICE_DIR}"
Environment="GPIOZERO_PIN_FACTORY=lgpio"
Environment="PYTHONUNBUFFERED=1"
ExecStart=/bin/bash ${DEVICE_DIR}/proscout_startup.sh
Restart=always
RestartSec=30
TimeoutStartSec=300
StandardOutput=append:${LOGS_DIR}/device-manager.log
StandardError=append:${LOGS_DIR}/device-manager.error.log

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=${INSTALL_DIR} /var/log /tmp

[Install]
WantedBy=multi-user.target
EOF

# Create log files
touch "${LOGS_DIR}/device-manager.log"
touch "${LOGS_DIR}/device-manager.error.log"
touch "${LOGS_DIR}/startup.log"
chown ${SERVICE_USER}:${SERVICE_USER} "${LOGS_DIR}/device-manager.log"
chown ${SERVICE_USER}:${SERVICE_USER} "${LOGS_DIR}/device-manager.error.log"
chown ${SERVICE_USER}:${SERVICE_USER} "${LOGS_DIR}/startup.log"

# Create enhanced management script
print_status "Creating enhanced management script..."
cat > "${SCRIPTS_DIR}/manage.sh" << EOF
#!/bin/bash

SERVICE_NAME="${SOFTWARE_NAME}"
LOGS_DIR="${LOGS_DIR}"
SCRIPTS_DIR="${SCRIPTS_DIR}"

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
    startup-logs)
        tail -f \$LOGS_DIR/startup.log
        ;;
    check-devices)
        echo "=== USB Device Information ==="
        lsusb
        echo ""
        echo "=== Serial Devices ==="
        ls -la /dev/ttyUSB* /dev/ttyACM* /dev/cdc-wdm* 2>/dev/null || echo "No serial devices found"
        echo ""
        echo "=== ModemManager Status ==="
        sudo mmcli -L
        echo ""
        echo "=== Network Connections ==="
        nmcli connection show
        echo ""
        echo "=== Active Network Interfaces ==="
        nmcli device status
        ;;
    check-permissions)
        echo "=== User Permissions ==="
        echo "Groups for ${SERVICE_USER}:"
        groups ${SERVICE_USER}
        echo ""
        echo "=== PolicyKit Rules ==="
        ls -la /etc/polkit-1/localauthority/50-local.d/modemmanager.pkla 2>/dev/null || echo "PolicyKit rules not found"
        echo ""
        echo "=== Device Permissions ==="
        ls -la /dev/ttyUSB* /dev/ttyACM* /dev/cdc-wdm* 2>/dev/null || echo "No serial devices found"
        ls -la /dev/video* 2>/dev/null || echo "No video devices found"
        echo ""
        echo "=== Udev Rules ==="
        ls -la /etc/udev/rules.d/99-*permissions.rules /etc/udev/rules.d/99-usb-no-suspend.rules 2>/dev/null || echo "No custom rules found"
        ;;
    detect-modem)
        echo "Running modem detection..."
        \$SCRIPTS_DIR/detect_modem.sh
        ;;
    setup-cellular)
        APN="\${2:-${USER_APN}}"
        echo "Setting up cellular with APN: \$APN"
        \$SCRIPTS_DIR/setup_cellular.sh "\$APN"
        ;;
    test-cellular)
        echo "Testing cellular connectivity:"
        if nmcli connection show --active | grep -q "gsm"; then
            echo "Cellular connection is active"
            ping -c 4 8.8.8.8
        else
            echo "No active cellular connection found"
            nmcli connection show | grep cellular || echo "No cellular connection configured"
        fi
        ;;
    monitor-cellular)
        echo "Running cellular connection monitor:"
        \$SCRIPTS_DIR/monitor_cellular.sh
        ;;
    cleanup-bearers)
        echo "Cleaning up duplicate bearers:"
        if mmcli -L | grep -q "/Modem/"; then
            mmcli -m 0 2>/dev/null | grep -o "/org/freedesktop/ModemManager1/Bearer/[0-9]*" | while read bearer_path; do
                bearer_num=\$(echo "\$bearer_path" | grep -o "[0-9]*\$")
                echo "Found bearer: \$bearer_num"
                if ! mmcli -b "\$bearer_num" 2>/dev/null | grep -q "connected: yes"; then
                    echo "Removing disconnected bearer \$bearer_num"
                    mmcli -m 0 --delete-bearer="\$bearer_num" 2>/dev/null
                fi
            done
        else
            echo "No modem detected"
        fi
        ;;
    reset-modem)
        echo "Resetting modem system..."
        sudo systemctl stop \$SERVICE_NAME
        sudo systemctl restart ModemManager
        sleep 10
        \$SCRIPTS_DIR/detect_modem.sh
        sudo systemctl start \$SERVICE_NAME
        ;;
    debug)
        echo "=== Debug Information ==="
        echo "Service status:"
        sudo systemctl status \$SERVICE_NAME --no-pager
        echo ""
        echo "Recent logs:"
        tail -20 \$LOGS_DIR/device-manager.log
        echo ""
        echo "Recent errors:"
        tail -20 \$LOGS_DIR/device-manager.error.log
        echo ""
        echo "USB devices:"
        lsusb
        echo ""
        echo "ModemManager:"
        sudo mmcli -L
        echo ""
        echo "Network status:"
        nmcli device status
        ;;
    *)
        echo "Usage: \$0 {start|stop|restart|status|logs|errors|startup-logs|check-devices|check-permissions|detect-modem|setup-cellular [APN]|test-cellular|monitor-cellular|cleanup-bearers|reset-modem|debug}"
        echo ""
        echo "Configured APN: ${USER_APN}"
        echo ""
        echo "Common commands:"
        echo "  \$0 debug                             # Show comprehensive debug info"
        echo "  \$0 detect-modem                     # Detect and initialize modem"
        echo "  \$0 setup-cellular                   # Setup cellular with configured APN"
        echo "  \$0 setup-cellular internet          # Setup with different APN"
        echo "  \$0 reset-modem                      # Reset entire modem system"
        echo "  \$0 test-cellular                    # Test cellular connectivity"
        exit 1
        ;;
esac
EOF

chmod +x "${SCRIPTS_DIR}/manage.sh"
chown ${SERVICE_USER}:${SERVICE_USER} "${SCRIPTS_DIR}/manage.sh"

# Set proper ownership for all files
chown -R ${SERVICE_USER}:${SERVICE_USER} "${INSTALL_DIR}"

# Enable and reload systemd service
print_status "Enabling systemd service..."
systemctl daemon-reload
systemctl enable ${SOFTWARE_NAME}

# Apply all udev rules
print_status "Applying udev rules..."
udevadm control --reload-rules
udevadm trigger

# Test dbus-python installation
print_status "Testing dbus-python installation..."
if sudo -u ${SERVICE_USER} "${VENV_DIR}/bin/python" -c "import dbus; print('dbus-python is working')" 2>/dev/null; then
    print_status "dbus-python test: SUCCESS"
else
    print_error "dbus-python test: FAILED"
    print_status "You may need to install dbus-python manually after reboot"
fi

# FIXED: Setup cellular connection with better error handling
if [ "$CELLULAR_SETUP_OPTION" -eq 1 ]; then
    print_status "Setting up cellular connection..."
    echo "Waiting for system services to be ready..."
    sleep 15
    
    # Check if modem is already detected before running setup
    if mmcli -L 2>/dev/null | grep -q "/Modem/"; then
        print_status "Modem already detected, proceeding with cellular setup..."
        
        # Run cellular setup
        if sudo -u ${SERVICE_USER} "${SCRIPTS_DIR}/setup_cellular.sh" "${USER_APN}"; then
            print_status "Cellular connection configured successfully!"
        else
            print_warning "Cellular setup failed. You can run it manually later with:"
            print_warning "  ${SCRIPTS_DIR}/manage.sh setup-cellular"
        fi
    else
        print_warning "Modem not detected yet. You can set up cellular after reboot with:"
        print_warning "  ${SCRIPTS_DIR}/manage.sh setup-cellular"
    fi
else
    print_status "Cellular setup postponed. To configure later, run:"
    print_status "  ${SCRIPTS_DIR}/manage.sh setup-cellular"
fi

print_status "Installation completed successfully!"
echo
echo "=== Installation Summary ==="
echo "Software installed to: ${INSTALL_DIR}"
echo "Service name: ${SOFTWARE_NAME}"
echo "Service user: ${SERVICE_USER}"
echo "Configured APN: ${USER_APN}"
echo "Device UUID: $(cat ${DEVICE_DIR}/device_id.txt)"
echo
echo "=== FIXES APPLIED ==="
echo "✅ Fixed modem detection logic (multiple detection methods)"
echo "✅ Fixed dbus-python installation issues"
echo "✅ Improved error handling and fallback mechanisms"
echo "✅ Enhanced cellular setup with better validation"
echo "✅ Added comprehensive debugging capabilities"
echo
echo "=== Service Management ==="
echo "Start service:    sudo systemctl start ${SOFTWARE_NAME}"
echo "Stop service:     sudo systemctl stop ${SOFTWARE_NAME}"
echo "Check status:     sudo systemctl status ${SOFTWARE_NAME}"
echo "View logs:        ${SCRIPTS_DIR}/manage.sh logs"
echo "Debug info:       ${SCRIPTS_DIR}/manage.sh debug"
echo
echo "=== Management Script ==="
echo "Location: ${SCRIPTS_DIR}/manage.sh"
echo "Key commands:"
echo "  ${SCRIPTS_DIR}/manage.sh debug           # Comprehensive debugging"
echo "  ${SCRIPTS_DIR}/manage.sh detect-modem   # Detect cellular modem"
echo "  ${SCRIPTS_DIR}/manage.sh setup-cellular # Configure cellular connection"
echo "  ${SCRIPTS_DIR}/manage.sh test-cellular  # Test cellular connectivity"
echo "  ${SCRIPTS_DIR}/manage.sh reset-modem    # Reset modem system"
echo
echo "=== Troubleshooting ==="
echo "If you encounter issues:"
echo "1. Check hardware: ${SCRIPTS_DIR}/manage.sh check-devices"
echo "2. Detect modem: ${SCRIPTS_DIR}/manage.sh detect-modem"
echo "3. Debug service: ${SCRIPTS_DIR}/manage.sh debug"
echo "4. Reset modem: ${SCRIPTS_DIR}/manage.sh reset-modem"
echo
echo "=== Next Steps ==="
echo "1. Reboot the system: sudo reboot"
echo "2. After reboot, check service: ${SCRIPTS_DIR}/manage.sh status"
echo "3. Test modem detection: ${SCRIPTS_DIR}/manage.sh detect-modem"
echo "4. Monitor logs: ${SCRIPTS_DIR}/manage.sh logs"
echo
if [ "$CELLULAR_SETUP_OPTION" -ne 1 ]; then
    echo "5. Setup cellular: ${SCRIPTS_DIR}/manage.sh setup-cellular"
    echo
fi

print_status "FIXED Installation script completed!"
print_status "This version should work much better than the previous one!"
print_warning "IMPORTANT: Please reboot the system for all changes to take effect!"
echo "Run: sudo reboot"
