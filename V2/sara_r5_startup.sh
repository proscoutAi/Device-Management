#!/bin/bash
# SARA-R5 Complete Startup Script with GPS streaming

LOG_FILE="/home/proscout/sara_r5_startup.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "========================================="
echo "$(date): Starting SARA-R5 services..."
echo "========================================="

# Clean start
echo "$(date): Stopping any existing gsmMuxd processes..."
sudo killall gsmMuxd 2>/dev/null
sleep 5

# Start GSM Multiplexer
echo "$(date): Starting GSM Multiplexer..."
sudo gsmMuxd &
sleep 15

# Wait for virtual devices to be ready
echo "$(date): Waiting for virtual devices..."
timeout=30
while [ $timeout -gt 0 ]; do
    if [ -e /dev/ttyGSM0 ] && [ -e /dev/ttyGSM1 ] && [ -e /dev/ttyGSM2 ]; then
        echo "$(date): Virtual devices ready"
        break
    fi
    sleep 1
    timeout=$((timeout-1))
done

# Configure GPS streaming using a more reliable method
echo "$(date): Configuring GPS streaming to ttyGSM2..."

# Create a temporary script to send AT commands
cat > /tmp/gps_config.txt << 'EOF'
AT+UGPRF=2
AT+USIO=2
AT+UGIND=1
AT+UGRMC=1
AT+UGGLL=1
AT+UGGSV=1
AT+UGGGA=1
AT+UGPS=1,1,67
EOF

# Send commands with proper formatting
while IFS= read -r cmd; do
    echo "$(date): Sending: $cmd"
    printf "%s\r\n" "$cmd" > /dev/ttyGSM0
    sleep 2
done < /tmp/gps_config.txt

# Clean up
rm /tmp/gps_config.txt

echo "$(date): GPS configuration completed"
sleep 5

# Start PPP
echo "$(date): Starting PPP connection..."
pon

echo "$(date): SARA-R5 startup completed"
echo "$(date): GPS data should now stream to /dev/ttyGSM2"
echo "$(date): Test with: timeout 30 cat /dev/ttyGSM2"
echo "========================================="

# Wait a bit for everything to stabilize
sleep 10

# Start ProScout Application
echo "$(date): Starting ProScout application..."
cd /home/proscout/ProScout-master/device-manager/
source /home/proscout/ProScout-master/ProScout-Device/bin/activate
nohup python3 main.py >> /var/log/proscout.log 2>&1 &
PROSCOUT_PID=$!
echo "$(date): ProScout application started with PID: $PROSCOUT_PID"