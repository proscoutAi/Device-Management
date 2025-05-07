# Install GPIO service and ensure proper permissions
print_status "Setting up GPIO service and permissions..."

# Install pigpio if not already installed
if ! command -v pigpiod &> /dev/null; then
    apt install -y pigpio
    print_status "Installed pigpio daemon"
fi

# Enable and start pigpio daemon
systemctl enable pigpiod
systemctl start pigpiod
print_status "Enabled and started pigpio daemon"

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
print_status "GPIO permissions configured"#!/bin/bash

# Complete installation script for Camera Management software
# For Raspberry Pi

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
SOFTWARE_NAME="camera-manager"
SERVICE_USER="proscout"
USER_HOME="/home/${SERVICE_USER}"
INSTALL_DIR="${USER_HOME}/${SOFTWARE_NAME}"
CONFIG_DIR="${INSTALL_DIR}/config"
VENV_DIR="${INSTALL_DIR}/venv"
LOGS_DIR="${INSTALL_DIR}/logs"
SCRIPTS_DIR="${INSTALL_DIR}/scripts"
GOOGLE_CREDS_FILE="${CONFIG_DIR}/google-credentials.json"

# Get current directory
CURRENT_DIR=$(pwd)

print_status "Starting installation..."

# Create user if doesn't exist and add to required groups
if ! id "${SERVICE_USER}" &>/dev/null; then
    print_status "Creating ${SERVICE_USER} user..."
    useradd -m -s /bin/bash "${SERVICE_USER}"
else
    print_status "User ${SERVICE_USER} already exists."
fi

# Make sure the user is in the required groups for GPIO and camera access
print_status "Adding user to required groups..."
usermod -aG video,dialout,gpio,i2c,spi "${SERVICE_USER}"

# Install system dependencies
print_status "Installing system dependencies..."
apt update
apt install -y python3-pip python3-venv python3-dev python3-opencv git curl unzip uuid-runtime \
    python3-gpiozero python3-rpi.gpio pigpio python3-pigpio i2c-tools

# Create directories
print_status "Creating directories..."
mkdir -p "${INSTALL_DIR}"
mkdir -p "${CONFIG_DIR}"
mkdir -p "${LOGS_DIR}"
mkdir -p "${SCRIPTS_DIR}"
chown -R ${SERVICE_USER}:${SERVICE_USER} "${INSTALL_DIR}"

# Copy Python files
print_status "Copying Python files..."
for file in *.py; do
    if [ -f "$file" ]; then
        cp "$file" "${INSTALL_DIR}/"
        chmod +x "${INSTALL_DIR}/$file"
        print_status "Copied $file"
    fi
done

# Copy requirements file or create a new one with correct encoding
print_status "Creating requirements.txt with UTF-8 encoding..."
# Create a fresh requirements file directly to avoid encoding issues
cat > "${INSTALL_DIR}/requirements.txt" << EOF
google-cloud-storage
opencv-python
exifread
tqdm
numpy
gpiozero
RPi.GPIO
pigpio
readchar
EOF
chown ${SERVICE_USER}:${SERVICE_USER} "${INSTALL_DIR}/requirements.txt"
print_status "Created requirements.txt with proper encoding"

# Create virtual environment
print_status "Creating virtual environment..."
sudo -u ${SERVICE_USER} python3 -m venv "${VENV_DIR}"

# Install dependencies
print_status "Installing Python dependencies..."
sudo -u ${SERVICE_USER} "${VENV_DIR}/bin/pip" install --upgrade pip
sudo -u ${SERVICE_USER} "${VENV_DIR}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

# Fix paths in Python files
print_status "Updating paths in Python files..."

# Fix path in session.py if it exists
if [ -f "${INSTALL_DIR}/session.py" ]; then
    sed -i "s|/Users/ronenrayten/Spray Detection MVP/SprayDetectionUnet/ProScout-master/camera/device_id.txt|${CONFIG_DIR}/device_id.txt|g" "${INSTALL_DIR}/session.py"
    print_status "Updated path in session.py"
fi

# Fix path in pylon_camera.py if it exists
if [ -f "${INSTALL_DIR}/pylon_camera.py" ]; then
    sed -i "s|/home/proscout/ProScout-master/camera/device_id.txt|${CONFIG_DIR}/device_id.txt|g" "${INSTALL_DIR}/pylon_camera.py"
    print_status "Updated path in pylon_camera.py"
fi

# Generate device UUID
if [ ! -f "${CONFIG_DIR}/device_id.txt" ]; then
    print_status "Generating device UUID..."
    uuidgen > "${CONFIG_DIR}/device_id.txt"
    chmod 600 "${CONFIG_DIR}/device_id.txt"
    chown ${SERVICE_USER}:${SERVICE_USER} "${CONFIG_DIR}/device_id.txt"
    print_status "Generated UUID: $(cat ${CONFIG_DIR}/device_id.txt)"
fi

# Set up Google Cloud authentication
print_status "Setting up Google Cloud authentication..."

# Copy service account key if it exists
SERVICE_ACCOUNT_KEY="${CURRENT_DIR}/hopeful-summer-438013-t5-8f165de61db2.json"
if [ -f "${SERVICE_ACCOUNT_KEY}" ]; then
    print_status "Found service account key in package"
    cp "${SERVICE_ACCOUNT_KEY}" "${GOOGLE_CREDS_FILE}"
    chmod 600 "${GOOGLE_CREDS_FILE}"
    chown ${SERVICE_USER}:${SERVICE_USER} "${GOOGLE_CREDS_FILE}"
    
    # Test authentication
    print_status "Testing Google Cloud authentication..."
    sudo -u ${SERVICE_USER} bash -c "export GOOGLE_APPLICATION_CREDENTIALS='${GOOGLE_CREDS_FILE}' && ${VENV_DIR}/bin/python -c \"
from google.cloud import storage
try:
    client = storage.Client()
    print('Successfully authenticated as ' + client.project)
except Exception as e:
    print('Authentication failed: ' + str(e))
    exit(1)
\""
    
    if [ $? -eq 0 ]; then
        print_status "Google Cloud authentication successful!"
    else
        print_warning "Authentication test failed. Check the service account key and permissions."
    fi
else
    print_warning "Service account key not found"
fi



# Create systemd service file
print_status "Creating systemd service..."
cat > "/etc/systemd/system/${SOFTWARE_NAME}.service" << EOF
[Unit]
Description=Camera Management Software
After=network-online.target pigpiod.service
Wants=network-online.target pigpiod.service

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
Environment="GOOGLE_APPLICATION_CREDENTIALS=${GOOGLE_CREDS_FILE}"
Environment="PYTHONPATH=${INSTALL_DIR}"
Environment="GPIOZERO_PIN_FACTORY=pigpio"
Environment="PIGPIO_ADDR=localhost"
ExecStart=${VENV_DIR}/bin/python ${INSTALL_DIR}/main.py
Restart=always
RestartSec=10
StandardOutput=append:${LOGS_DIR}/camera-manager.log
StandardError=append:${LOGS_DIR}/camera-manager.error.log

[Install]
WantedBy=multi-user.target
EOF

# Create log files
touch "${LOGS_DIR}/camera-manager.log"
touch "${LOGS_DIR}/camera-manager.error.log"
chown ${SERVICE_USER}:${SERVICE_USER} "${LOGS_DIR}/camera-manager.log"
chown ${SERVICE_USER}:${SERVICE_USER} "${LOGS_DIR}/camera-manager.error.log"

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
        tail -f \$LOGS_DIR/camera-manager.log
        ;;
    errors)
        tail -f \$LOGS_DIR/camera-manager.error.log
        ;;
    *)
        echo "Usage: \$0 {start|stop|restart|status|logs|errors}"
        exit 1
        ;;
esac
EOF
chmod +x "${SCRIPTS_DIR}/manage.sh"

# Create symbolic link for convenience
ln -sf "${SCRIPTS_DIR}/manage.sh" "${USER_HOME}/manage-camera.sh"
chown ${SERVICE_USER}:${SERVICE_USER} "${USER_HOME}/manage-camera.sh"

# Enable and start service
print_status "Enabling and starting service..."
systemctl daemon-reload
systemctl enable ${SOFTWARE_NAME}
systemctl start ${SERVICE_NAME}

# Check service status
print_status "Checking service status..."
sleep 3
if systemctl is-active --quiet ${SOFTWARE_NAME}; then
    print_status "Service is running successfully!"
else
    print_error "Service failed to start. Checking logs:"
    journalctl -u ${SERVICE_NAME} -n 20
    echo ""
    print_error "You can view more logs with:"
    print_error "sudo journalctl -u ${SERVICE_NAME}"
    print_error "tail -f ${LOGS_DIR}/camera-manager.error.log"
fi

print_status "Installation complete!"
