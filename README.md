# ProScout Device Management System

A comprehensive IoT data collection and transmission system designed for Raspberry Pi Zero W2. This system collects GPS, IMU, camera, and flow meter data and transmits it to cloud services via cellular connectivity.

## Table of Contents

- [Overview](#overview)
- [Hardware Requirements](#hardware-requirements)
- [Software Requirements](#software-requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Maintenance](#maintenance)

## Overview

The ProScout Device Management System is designed to:
- Collect real-time GPS location data from a dual-band GPS module
- Monitor orientation and movement via IMU (accelerometer, gyroscope, magnetometer)
- Capture images from a connected camera (optional)
- Measure flow rates using a pulse-based flow meter (optional)
- Transmit collected data to cloud services via cellular connectivity (SARA-R5 modem)
- Provide visual status feedback through LED indicators
- Handle offline data storage and automatic retry when connectivity is restored

## Hardware Requirements

### Core Components
- **Raspberry Pi Zero W2** - Main processing unit
- **OzzMaker SARA-R5 Modem** - Cellular connectivity and GPS source
- **Dual Band GPS Module** - USB to UART GPS receiver (backup/additional GPS)
- **OzzMaker LTE IMU ALT** - I2C IMU module containing:
  - LSM6DSL (accelerometer + gyroscope)
  - MMC5983MA (magnetometer)

### Optional Components
- **USB Camera** - For image capture
- **Flow Meter** - Pulse-based flow sensor connected to GPIO pin 5

### GPIO Pin Assignments
- **GPIO 5** - Flow meter pulse input
- **GPIO 17** - Blue LED indicator
- **I2C Bus** - IMU communication (LSM6DSL at 0x6A, MMC5983MA at 0x30)

## Software Requirements

### Operating System
- Raspberry Pi OS (32-bit or 64-bit)
- Python 3.7 or higher

### Python Dependencies
- `requests` - HTTP client for cloud uploads
- `pyserial` - Serial communication
- `gps3` / `pynmea2` - GPS data parsing
- `psutil` - System monitoring
- `opencv-python-headless` - Camera support
- `numpy` - Image processing
- `RPi.GPIO` / `gpiozero` - GPIO control
- `smbus` / `smbus2` - I2C communication
- `lgpio` - GPIO library for flow meter

### System Packages
- `ppp` - Point-to-Point Protocol for cellular connection
- `git` - Version control
- `python3-pip` - Python package manager
- `python3-venv` - Python virtual environment support

## Installation

### Step 1: Initial System Setup

1. **Flash Raspberry Pi OS** to a microSD card
2. **Enable SSH** and configure WiFi (if needed)
3. **Create user `proscout`**:
   ```bash
   sudo useradd -m -s /bin/bash proscout
   sudo passwd proscout
   ```

4. **Login as `proscout` user**

### Step 2: Install SARA-R5 Modem Support

Run the SARA-R5 installation script:

```bash
cd ~
wget https://raw.githubusercontent.com/proscoutAi/Device-Management/main/scripts/sara-r5-installation.sh
chmod +x sara-r5-installation.sh
./sara-r5-installation.sh
```

This script will:
- Configure serial interfaces
- Install and compile `gsmMuxd` for GSM multiplexing
- Set up PPP for cellular connectivity
- Configure GPS routing through the modem
- Enable I2C for IMU communication
- Create startup scripts and cron jobs

**Important**: After the first reboot, run the GPS initial configuration:
```bash
~/configure_gps_initial.sh
```
This only needs to be run once.

### Step 3: Install ProScout Software

Run the software installation script:

```bash
cd ~
wget https://raw.githubusercontent.com/proscoutAi/Device-Management/main/scripts/software_install.sh
chmod +x software_install.sh
./software_install.sh
```

This script will:
- Install system dependencies
- Clone the ProScout repository
- Create a Python virtual environment
- Install Python packages
- Configure automatic startup
- Set up logging

### Step 4: Install LED Service (Optional)

If you have LED indicators connected:

```bash
cd /home/proscout/ProScout-master/Device-Management/leds_manager
chmod +x install_leds_service.sh
sudo ./install_leds_service.sh
```

### Step 5: Configure the System

1. **Create configuration file**:
   ```bash
   cd /home/proscout/ProScout-master/Device-Management
   cp config.example.ini config.ini
   nano config.ini
   ```

2. **Create device ID file**:
   ```bash
   cp device_id.example.txt device_id.txt
   nano device_id.txt
   ```
   Enter your unique device identifier (UUID format recommended).

3. **Configure PPP credentials** (if required):
   ```bash
   sudo nano /etc/ppp/chap-secrets
   ```

## Configuration

### config.ini

Edit `/home/proscout/ProScout-master/Device-Management/config.ini`:

```ini
[Setup]
sleep_interval = 1                    # Data collection interval in seconds
production = False                    # Use production cloud endpoint
camera = False                        # Enable camera capture
flow_meter = False                    # Enable flow meter
imu = True                            # Enable IMU
cloud_function_url_stg = https://...  # Staging endpoint URL
cloud_function_url_prod = https://... # Production endpoint URL
batch_size = 5                        # Number of samples per upload batch
imu_rate_per_second = 2               # IMU sampling rate (Hz)
flow_meter_pulses_per_litter = 660    # Flow meter calibration
```

### Configuration Options

- **sleep_interval**: How often to collect and upload data (in seconds)
- **production**: Set to `True` for production, `False` for staging
- **camera**: Enable/disable camera image capture
- **flow_meter**: Enable/disable flow meter readings
- **imu**: Enable/disable IMU data collection
- **batch_size**: Number of data samples to batch before uploading
- **imu_rate_per_second**: IMU sampling frequency
- **flow_meter_pulses_per_litter**: Calibration constant for flow meter

### device_id.txt

Contains a unique identifier for your device (UUID format recommended):
```
91010af7-ef32-4771-adfd-2e87a46e0d2a
```

## Usage

### Starting the System

The system starts automatically on boot via the startup scripts. To manually start:

```bash
cd /home/proscout/ProScout-master/Device-Management
source ../ProScout-Device/bin/activate
python3 main.py
```

### Checking System Status

**Check application logs**:
```bash
tail -f /var/log/proscout.log
```

**Check SARA-R5 startup logs**:
```bash
tail -f /home/proscout/sara_r5_startup.log
```

**Check connection status**:
```bash
~/check_connection.sh
```

**Check GPS data**:
```bash
~/check_gps.sh
```

**Check system processes**:
```bash
ps aux | grep -E "python|gsmMuxd|pppd"
```

### Stopping the System

To stop the application:
```bash
pkill -f "python3 main.py"
```

To stop all services:
```bash
sudo poff -a
sudo pkill -f gsmMuxd
```

### Manual Operations

**Start PPP connection manually**:
```bash
pon
```

**Stop PPP connection**:
```bash
sudo poff -a
```

**Restart SARA-R5 services**:
```bash
~/sara_r5_startup.sh
```

**Set network priority** (PPP over WiFi):
```bash
~/set_network_priority.sh
```

## Project Structure

```
Device-Management/
├── main.py                 # Main application entry point
├── session.py              # Data collection session manager
├── upload.py               # Cloud upload client with offline support
├── config.example.ini      # Configuration template
├── device_id.example.txt   # Device ID template
│
├── gps_manager.py          # GPS data collection (dual band USB GPS)
├── IMU_manager.py          # IMU data collection and processing
├── camera.py               # Camera capture functionality
├── flow_meter.py           # Flow meter pulse counting
│
├── LSM6DSL.py              # LSM6DSL accelerometer/gyroscope driver
├── MMC5983MA.py            # MMC5983MA magnetometer driver
│
├── calibrate/              # IMU calibration utilities
│   ├── IMU_calibration.py
│   ├── IMU.py
│   ├── LSM6DSL.py
│   └── MMC5983MA.py
│
├── leds_manager/           # LED status indicator service
│   ├── leds_service.py
│   ├── button_led_manager.py
│   ├── install_leds_service.sh
│   └── leds-service.service
│
└── scripts/                # Installation and utility scripts
    ├── sara-r5-installation.sh    # SARA-R5 modem setup
    ├── software_install.sh        # Software installation
    ├── modem-complete-start.sh    # Modem startup script
    └── upload_files.sh            # File upload utility
```

## Troubleshooting

### GPS Issues

**Problem**: No GPS fix
- **Solution**: Ensure GPS antenna has clear view of sky
- Check GPS data stream: `~/check_gps.sh`
- Verify SARA-R5 GPS is enabled: `echo -e "AT+UGPS?\r" > /dev/ttyGSM0`

**Problem**: GPS data not updating
- **Solution**: Check if `/dev/ttyGSM2` exists and has data
- Restart GPS: `echo -e "AT+UGPS=1,0,67\r" > /dev/ttyGSM0`

### Cellular Connectivity Issues

**Problem**: No PPP connection
- **Solution**: 
  - Check APN configuration in `/etc/ppp/peers/provider`
  - Verify SIM card is active and has data plan
  - Check signal strength: `echo -e "AT+CSQ\r" > /dev/ttyGSM0`
  - Review PPP logs: `sudo tail -f /var/log/syslog | grep ppp`

**Problem**: Connection drops frequently
- **Solution**: 
  - Check signal quality
  - Verify APN settings match your carrier
  - Check for interference or poor antenna placement

### IMU Issues

**Problem**: IMU not detected
- **Solution**:
  - Verify I2C is enabled: `sudo raspi-config` → Interface Options → I2C
  - Check I2C devices: `i2cdetect -y 1`
  - Verify connections (SDA/SCL)
  - Check power supply to IMU module

**Problem**: IMU data seems incorrect
- **Solution**: 
  - Recalibrate IMU: Run calibration script in `calibrate/` directory
  - Check for magnetic interference
  - Verify IMU is securely mounted

### Camera Issues

**Problem**: Camera not detected
- **Solution**:
  - Check USB connection
  - Verify camera is recognized: `lsusb`
  - Test camera: `python3 -c "import cv2; cap = cv2.VideoCapture(0); print(cap.isOpened())"`

### Flow Meter Issues

**Problem**: No pulse counts
- **Solution**:
  - Verify GPIO 5 connection
  - Check wiring (signal, ground, power)
  - Test with multimeter for signal changes
  - Review flow meter logs in application output

### Application Not Starting

**Problem**: Application fails to start
- **Solution**:
  - Check Python virtual environment is activated
  - Verify `config.ini` exists and is valid
  - Check `device_id.txt` exists
  - Review logs: `tail -f /var/log/proscout.log`
  - Verify all dependencies are installed

### Data Upload Issues

**Problem**: Data not uploading
- **Solution**:
  - Check internet connectivity: `ping 8.8.8.8`
  - Verify cloud function URLs in `config.ini`
  - Check offline data directory: `ls -la /home/proscout/offline_data`
  - Review upload logs in application output

## Maintenance

### Log Files

- **Application log**: `/var/log/proscout.log`
- **SARA-R5 startup log**: `/home/proscout/sara_r5_startup.log`
- **System log**: `/var/log/syslog`
- **PPP log**: Check syslog for ppp entries

### Offline Data

Offline data is stored in `/home/proscout/offline_data/` when uploads fail. The system automatically retries uploading this data when connectivity is restored.

### System Updates

To update the software:

```bash
cd /home/proscout/ProScout-master/Device-Management
git pull
source ../ProScout-Device/bin/activate
pip install -r requirements.txt  # If requirements.txt exists
```

### IMU Calibration

Periodic IMU calibration may be needed. Run the calibration script:

```bash
cd /home/proscout/ProScout-master/Device-Management/calibrate
source ../../ProScout-Device/bin/activate
python3 IMU_calibration.py
```

### Backup Configuration

Regularly backup your configuration:
```bash
cp /home/proscout/ProScout-master/Device-Management/config.ini ~/config.backup
cp /home/proscout/ProScout-master/Device-Management/device_id.txt ~/device_id.backup
```

## Data Format

The system collects and transmits data in the following format:

```json
{
  "device_uuid": "device-id-here",
  "sessionTimestamp": "2024-01-01T00:00:00",
  "sleep_time": 1,
  "payload": [
    {
      "timestamp": "2024-01-01T00:00:00",
      "flow_meter_counter": 0.0,
      "latitude": 0.0,
      "longitude": 0.0,
      "speed_kmh": 0.0,
      "heading": 0.0,
      "IMU": [
        {
          "GYRx": 0.0,
          "GYRy": 0.0,
          "GYRz": 0.0,
          "MAGx": 0.0,
          "MAGy": 0.0,
          "MAGz": 0.0,
          "ACCx": 0.0,
          "ACCy": 0.0,
          "ACCz": 0.0,
          "heading_compensated_deg": 0.0
        }
      ],
      "image_base_64": "base64-encoded-image-or-null",
      "gps_fix": true
    }
  ]
}
```

## Support

For issues, questions, or contributions, please refer to the project repository or contact the development team.

## License

[Add license information here]

---

**Last Updated**: 2024
**Target Platform**: Raspberry Pi Zero W2
**Python Version**: 3.7+
