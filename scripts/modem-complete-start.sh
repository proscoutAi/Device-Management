#!/bin/bash
# /usr/local/bin/modem-complete-start.sh

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
timeout=10
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

# Initialize GPS on ttyGSM1
log_message "Initializing GPS..."
echo -e "AT+UGPS=1,4,67\r\n" > /dev/ttyGSM0
sleep 3

# Read GPS response (optional)
sudo timeout 3 cat /dev/ttyGSM2 > /tmp/gps_response 2>/dev/null || true
if [ -s /tmp/gps_response ]; then
    response=$(cat /tmp/gps_response | tr -d '\r' | grep -v '^$' | tail -1)
    log_message "GPS response: $response"
fi

# Start PPP
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
source /home/proscout/ProScout-master/ProScout-Device/bin/activate
cd  /home/proscout/ProScout-master/device-manager/
python3 main.py >> /var/log/proscout.log 2>&1