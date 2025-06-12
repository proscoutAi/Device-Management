#!/bin/bash

initialize_gps() {
	echo "=== Manual GPS initialization ==="
        echo "systemctl stop ModemManager"
	sudo systemctl stop ModemManager
	sleep 5

	sudo stty -F /dev/ttyUSB3 115200 raw -echo -cstopb 2>/dev/null
	printf "AT+CGNSPWR=0\r\n" | sudo tee /dev/ttyUSB3 >/dev/null 2>&1
	sleep 2
	printf "AT+CGNSPWR=1\r\n" | sudo tee /dev/ttyUSB3 >/dev/null 2>&1
	sleep 3
	printf "AT+CGNSTST=1\r\n" | sudo tee /dev/ttyUSB3 >/dev/null 2>&1
	sleep 3
        echo "systemctl start ModemManager"
	sudo systemctl start ModemManager
	sleep 30

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




# Initialize GPS first
initialize_gps
gps_status=$?

if [ $gps_status -eq 0 ]; then
    echo "GPS initialization completed successfully"
else
    echo "GPS initialization failed, but continuing with main application"
fi

# Activate virtual environment
echo "Activating Python virtual environment..."
source /home/proscout/ProScout-master/ProScout-Camera/bin/activate

# Set up GCP authentication
echo "Setting up GCP authentication..."
export GOOGLE_APPLICATION_CREDENTIALS="/home/proscout/gcp-credentials.json"

# Change to the camera directory where config.ini is located
cd /home/proscout/ProScout-master/camera

# Run your Python script
echo "Starting ProScout main application..."
python3 main.py
