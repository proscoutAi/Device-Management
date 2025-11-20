#!/usr/bin/python
#   This script is used to calibrate the compass on an OzzMaker SARA-R5 LTE-M GPS + 10DOF board.
#
#   Start this program and rotate your board in all directions.
#   You will see the maximum and minimum values change.
#   After about 30secs or when the values are not changing, press Ctrl-C.
#   The script will printout some text which you then need to add to
#   ozzmaker-LTE-IMU.py or ozzmaker-LTE-IMU-simple.py
#
#
#
#   Feel free to do whatever you like with this code.
#   Distributed as-is; no warranty is given.
#
#   http://ozzmaker.com/


import argparse
import datetime
import logging
import math
import os
import signal
import sys
import threading
import time

import IMU as IMU
from gpiozero import LED

# GPIO pin 21 for LED
LED_PIN = 21
IMU_VALUES_FILE = "IMU_values"
ITERATION_THRESHOLD = 150
MAX_CHANGES_ALLOWED = 5

# Parse command line arguments
parser = argparse.ArgumentParser(description='Calibrate IMU compass')
parser.add_argument('--debug', action='store_true', help='Enable debug logging')
args = parser.parse_args()

# Setup logging
log_level = logging.DEBUG if args.debug else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize LED
led = LED(LED_PIN)

# Turn on LED on startup
led.on()

# Thread control for LED blinking
blink_thread = None
blink_stop_event = threading.Event()

def blink_led_continuously():
    """Continuously blink LED until stop event is set"""
    while not blink_stop_event.is_set():
        led.on()
        time.sleep(0.1)
        if not blink_stop_event.is_set():
            led.off()
            time.sleep(0.1)

def load_imu_values():
    """Load IMU calibration values from file if it exists"""
    if os.path.exists(IMU_VALUES_FILE):
        try:
            with open(IMU_VALUES_FILE, 'r') as f:
                lines = f.readlines()
                values = {}
                for line in lines:
                    if '=' in line:
                        key, value = line.strip().split('=')
                        values[key.strip()] = int(value.strip())
                return values
        except Exception as e:
            logger.error(f"Error reading IMU_values file: {e}")
            return None
    return None

def save_imu_values():
    """Save current max IMU values to file"""
    try:
        with open(IMU_VALUES_FILE, 'w') as f:
            f.write(f"magXmin = {magXmin}\n")
            f.write(f"magYmin = {magYmin}\n")
            f.write(f"magZmin = {magZmin}\n")
            f.write(f"magXmax = {magXmax}\n")
            f.write(f"magYmax = {magYmax}\n")
            f.write(f"magZmax = {magZmax}\n")
        logger.info(f"Calibration values saved to {IMU_VALUES_FILE}")
        return True
    except Exception as e:
        logger.error(f"Error saving IMU_values file: {e}")
        return False

def handle_ctrl_c(signal, frame):
    logger.debug("magXmin = %i" % (magXmin))
    logger.debug("magYmin = %i" % (magYmin))
    logger.debug("magZmin = %i" % (magZmin))
    logger.debug("magXmax = %i" % (magXmax))
    logger.debug("magYmax = %i" % (magYmax))
    logger.debug("magZmax = %i" % (magZmax))
    # Stop blinking thread if running
    global blink_thread
    if blink_thread and blink_thread.is_alive():
        blink_stop_event.set()
        blink_thread.join(timeout=0.5)
    led.off()
    sys.exit(130) # 130 is standard exit code for ctrl-c


IMU.detectIMU()
IMU.initIMU()

#This will capture exit when using Ctrl-C
signal.signal(signal.SIGINT, handle_ctrl_c)

# Load previous values if file exists
saved_values = load_imu_values()
if saved_values:
    logger.info("Loaded previous calibration values from file")
    logger.debug(f"  magXmin = {saved_values.get('magXmin', 'N/A')}")
    logger.debug(f"  magYmin = {saved_values.get('magYmin', 'N/A')}")
    logger.debug(f"  magZmin = {saved_values.get('magZmin', 'N/A')}")
    logger.debug(f"  magXmax = {saved_values.get('magXmax', 'N/A')}")
    logger.debug(f"  magYmax = {saved_values.get('magYmax', 'N/A')}")
    logger.debug(f"  magZmax = {saved_values.get('magZmax', 'N/A')}")
    
    # Set min and max values from file
    magXmin = saved_values.get('magXmin', 9999999)
    magYmin = saved_values.get('magYmin', 999999)
    magZmin = saved_values.get('magZmin', 999999)
    magXmax = saved_values.get('magXmax', -999999)
    magYmax = saved_values.get('magYmax', -999999)
    magZmax = saved_values.get('magZmax', -999999)
else:
    #Preload the variables used to keep track of the minimum and maximum values
    magXmin = 9999999
    magYmin = 999999
    magZmin = 999999
    magXmax = -999999
    magYmax = -999999
    magZmax = -999999

# Variables to track calibration progress
iteration_counter = 0
change_counter = 0
last_magXmin = magXmin
last_magYmin = magYmin
last_magZmin = magZmin
last_magXmax = magXmax
last_magYmax = magYmax
last_magZmax = magZmax

SKIP = 1
values_after_skip = None

while True:
    try:
        if(SKIP):                       #discard the first few readings 
            for i in range(10):
                MAGx = IMU.readMAGx()
                MAGy = IMU.readMAGy()
                MAGz = IMU.readMAGz()
            SKIP = 0
            
            # After skip, start blinking LED for calibration
            logger.info("Starting calibration - LED will blink during calibration")
            blink_stop_event.clear()
            blink_thread = threading.Thread(target=blink_led_continuously, daemon=True)
            blink_thread.start()
            
            # After skip, read values and compare with saved values
            MAGx = IMU.readMAGx()
            MAGy = IMU.readMAGy()
            MAGz = IMU.readMAGz()
            values_after_skip = (MAGx, MAGy, MAGz)
            
            if saved_values:
                # Check if values are different from saved values
                # Compare current readings with saved min/max ranges
                saved_magXmin = saved_values.get('magXmin', 0)
                saved_magXmax = saved_values.get('magXmax', 0)
                saved_magYmin = saved_values.get('magYmin', 0)
                saved_magYmax = saved_values.get('magYmax', 0)
                saved_magZmin = saved_values.get('magZmin', 0)
                saved_magZmax = saved_values.get('magZmax', 0)
                
                # Check if current readings are outside the saved range (with tolerance)
                tolerance = 100
                outside_range = (
                    MAGx < (saved_magXmin - tolerance) or MAGx > (saved_magXmax + tolerance) or
                    MAGy < (saved_magYmin - tolerance) or MAGy > (saved_magYmax + tolerance) or
                    MAGz < (saved_magZmin - tolerance) or MAGz > (saved_magZmax + tolerance)
                )
                
                if outside_range:
                    logger.info("Values after skip differ from saved values. Calibration needed.")

        #Read magnetometer values
        MAGx = IMU.readMAGx()
        MAGy = IMU.readMAGy()
        MAGz = IMU.readMAGz()
    
        if MAGx > magXmax:
            magXmax = MAGx
        if MAGy > magYmax:
            magYmax = MAGy
        if MAGz > magZmax:
            magZmax = MAGz
        if MAGx < magXmin:
            magXmin = MAGx
        if MAGy < magYmin:
            magYmin = MAGy
        if MAGz < magZmin:
            magZmin = MAGz

        # Check if values have changed
        values_changed = not (magXmin == last_magXmin and magYmin == last_magYmin and magZmin == last_magZmin and
                              magXmax == last_magXmax and magYmax == last_magYmax and magZmax == last_magZmax)
        
        if values_changed:
            change_counter += 1
            last_magXmin = magXmin
            last_magYmin = magYmin
            last_magZmin = magZmin
            last_magXmax = magXmax
            last_magYmax = magYmax
            last_magZmax = magZmax
        
        iteration_counter += 1

        # Check if we've reached 300 iterations
        if iteration_counter >= ITERATION_THRESHOLD:
            # If we have 5 or fewer changes in 300 iterations, calibration is complete
            if change_counter <= MAX_CHANGES_ALLOWED:
                # Stop blinking thread
                if blink_thread and blink_thread.is_alive():
                    blink_stop_event.set()
                    blink_thread.join(timeout=0.5)
                
                if save_imu_values():
                    logger.info("Calibration complete! Values saved.")
                    logger.info(f"Completed {iteration_counter} iterations with {change_counter} changes.")
                    led.off()  # Turn off LED when calibration is complete
                    logger.info("Exiting script...")
                    sys.exit(0)
            else:
                # Too many changes, reset counters and continue
                logger.info(f"Too many changes ({change_counter} > {MAX_CHANGES_ALLOWED}). Resetting and continuing...")
                iteration_counter = 0
                change_counter = 0
                # Reset last values to current values to start fresh
                last_magXmin = magXmin
                last_magYmin = magYmin
                last_magZmin = magZmin
                last_magXmax = magXmax
                last_magYmax = magYmax
                last_magZmax = magZmax

        logger.debug("magXmin  %i  magYmin  %i  magZmin  %i  ## magXmax  %i  magYmax  %i  magZmax %i  (iterations: %i, changes: %i)" %(magXmin,magYmin,magZmin,magXmax,magYmax,magZmax, iteration_counter, change_counter))

        #slow program down a bit, makes the output more readable
        time.sleep(0.03)
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
        time.sleep(0.03)
        continue