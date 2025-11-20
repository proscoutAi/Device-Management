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
import logging
import os
import signal
import sys
import threading
import time

import IMU as IMU
from gpiozero import LED


class IMUCalibrator:
    """Calibrates IMU compass by tracking min/max magnetometer values."""
    
    # Calibration constants
    ITERATION_THRESHOLD = 150
    MAX_CHANGES_ALLOWED = 5
    INITIAL_SKIP_READINGS = 10
    TOLERANCE = 100
    LOOP_DELAY = 0.03
    
    def __init__(self, save_path, led_gpio=None):
        """
        Initialize the IMU calibrator.
        
        Args:
            save_path (str): Path where to save the IMU calibration values
            led_gpio (int, optional): GPIO pin number for LED. If None, LED is not used.
        """
        self.save_path = save_path
        self.led_gpio = led_gpio
        self.led = None
        self.blink_thread = None
        self.blink_stop_event = threading.Event()
        
        # Initialize LED if GPIO is provided and turn it on solid at startup
        if self.led_gpio is not None:
            try:
                self.led = LED(self.led_gpio)
                self.led.on()  # Turn LED on solid when script starts
            except Exception as e:
                logging.warning(f"Failed to initialize LED on GPIO {self.led_gpio}: {e}")
                self.led = None
        
        # Track if calibration is needed
        self.calibration_needed = False
        
        # Initialize magnetometer min/max values
        self.magXmin = 9999999
        self.magYmin = 999999
        self.magZmin = 999999
        self.magXmax = -999999
        self.magYmax = -999999
        self.magZmax = -999999
        
        # Calibration progress tracking
        self.iteration_counter = 0
        self.change_counter = 0
        self.last_magXmin = self.magXmin
        self.last_magYmin = self.magYmin
        self.last_magZmin = self.magZmin
        self.last_magXmax = self.magXmax
        self.last_magYmax = self.magYmax
        self.last_magZmax = self.magZmax
        
        # Skip flag for initial readings
        self.skip_initial_readings = True
        
        # Setup signal handler
        signal.signal(signal.SIGINT, self._handle_ctrl_c)
    
    def _blink_led_continuously(self):
        """Continuously blink LED until stop event is set."""
        if self.led is None:
            return
        
        while not self.blink_stop_event.is_set():
            self.led.on()
            time.sleep(0.1)
            if not self.blink_stop_event.is_set():
                self.led.off()
                time.sleep(0.1)
    
    def _turn_led_solid(self):
        """Turn LED on solid (stop blinking if active)."""
        if self.led is None:
            return
        
        # Stop blinking if active
        if self.blink_thread and self.blink_thread.is_alive():
            self.blink_stop_event.set()
            self.blink_thread.join(timeout=0.5)
        
        # Turn LED on solid
        self.led.on()
    
    def _start_led_blinking(self):
        """Start LED blinking in a separate thread."""
        if self.led is None:
            return
        
        # Stop any solid state first
        if self.blink_thread and self.blink_thread.is_alive():
            self.blink_stop_event.set()
            self.blink_thread.join(timeout=0.5)
        
        self.blink_stop_event.clear()
        self.blink_thread = threading.Thread(target=self._blink_led_continuously, daemon=True)
        self.blink_thread.start()
    
    def _stop_led_blinking(self):
        """Stop LED blinking and turn off LED."""
        if self.led is None:
            return
        
        if self.blink_thread and self.blink_thread.is_alive():
            self.blink_stop_event.set()
            self.blink_thread.join(timeout=0.5)
        self.led.off()
    
    def _load_imu_values(self):
        """Load IMU calibration values from file if it exists."""
        if not os.path.exists(self.save_path):
            return None
        
        try:
            with open(self.save_path, 'r') as f:
                lines = f.readlines()
                values = {}
                for line in lines:
                    if '=' in line:
                        key, value = line.strip().split('=')
                        values[key.strip()] = int(value.strip())
                return values
        except Exception as e:
            logging.error(f"Error reading IMU values file: {e}")
            return None
    
    def _save_imu_values(self):
        """Save current max IMU values to file."""
        try:
            with open(self.save_path, 'w') as f:
                f.write(f"magXmin = {self.magXmin}\n")
                f.write(f"magYmin = {self.magYmin}\n")
                f.write(f"magZmin = {self.magZmin}\n")
                f.write(f"magXmax = {self.magXmax}\n")
                f.write(f"magYmax = {self.magYmax}\n")
                f.write(f"magZmax = {self.magZmax}\n")
            logging.info(f"Calibration values saved to {self.save_path}")
            return True
        except Exception as e:
            logging.error(f"Error saving IMU values file: {e}")
            return False
    
    def _handle_ctrl_c(self, signal, frame):
        """Handle Ctrl-C signal by saving values and exiting."""
        logging.debug("magXmin = %i" % (self.magXmin))
        logging.debug("magYmin = %i" % (self.magYmin))
        logging.debug("magZmin = %i" % (self.magZmin))
        logging.debug("magXmax = %i" % (self.magXmax))
        logging.debug("magYmax = %i" % (self.magYmax))
        logging.debug("magZmax = %i" % (self.magZmax))
        
        self._stop_led_blinking()
        sys.exit(130)  # 130 is standard exit code for ctrl-c
    
    def _initialize_values(self):
        """Initialize min/max values from saved file or use defaults."""
        saved_values = self._load_imu_values()
        
        if saved_values:
            logging.info("Loaded previous calibration values from file")
            logging.debug(f"  magXmin = {saved_values.get('magXmin', 'N/A')}")
            logging.debug(f"  magYmin = {saved_values.get('magYmin', 'N/A')}")
            logging.debug(f"  magZmin = {saved_values.get('magZmin', 'N/A')}")
            logging.debug(f"  magXmax = {saved_values.get('magXmax', 'N/A')}")
            logging.debug(f"  magYmax = {saved_values.get('magYmax', 'N/A')}")
            logging.debug(f"  magZmax = {saved_values.get('magZmax', 'N/A')}")
            
            self.magXmin = saved_values.get('magXmin', 9999999)
            self.magYmin = saved_values.get('magYmin', 999999)
            self.magZmin = saved_values.get('magZmin', 999999)
            self.magXmax = saved_values.get('magXmax', -999999)
            self.magYmax = saved_values.get('magYmax', -999999)
            self.magZmax = saved_values.get('magZmax', -999999)
            
            # Update last values
            self.last_magXmin = self.magXmin
            self.last_magYmin = self.magYmin
            self.last_magZmin = self.magZmin
            self.last_magXmax = self.magXmax
            self.last_magYmax = self.magYmax
            self.last_magZmax = self.magZmax
    
    def _check_values_changed(self):
        """Check if calibration values have changed and update counters."""
        values_changed = not (
            self.magXmin == self.last_magXmin and
            self.magYmin == self.last_magYmin and
            self.magZmin == self.last_magZmin and
            self.magXmax == self.last_magXmax and
            self.magYmax == self.last_magYmax and
            self.magZmax == self.last_magZmax
        )
        
        if values_changed:
            self.change_counter += 1
            self.last_magXmin = self.magXmin
            self.last_magYmin = self.magYmin
            self.last_magZmin = self.magZmin
            self.last_magXmax = self.magXmax
            self.last_magYmax = self.magYmax
            self.last_magZmax = self.magZmax
    
    def _check_calibration_complete(self):
        """Check if calibration is complete based on iteration and change thresholds."""
        if self.iteration_counter >= self.ITERATION_THRESHOLD:
            if self.change_counter <= self.MAX_CHANGES_ALLOWED:
                self._stop_led_blinking()
                if self._save_imu_values():
                    logging.info("Calibration complete! Values saved.")
                    logging.info(f"Completed {self.iteration_counter} iterations with {self.change_counter} changes.")
                    logging.info("Exiting script...")
                    return True
            else:
                # Too many changes, reset counters and continue
                logging.info(f"Too many changes ({self.change_counter} > {self.MAX_CHANGES_ALLOWED}). Resetting and continuing...")
                self.iteration_counter = 0
                self.change_counter = 0
                # Reset last values to current values to start fresh
                self.last_magXmin = self.magXmin
                self.last_magYmin = self.magYmin
                self.last_magZmin = self.magZmin
                self.last_magXmax = self.magXmax
                self.last_magYmax = self.magYmax
                self.last_magZmax = self.magZmax
        
        return False
    
    def _check_if_calibration_needed(self, MAGx, MAGy, MAGz):
        """Check if calibration is needed based on current readings vs saved values."""
        saved_values = self._load_imu_values()
        
        # If no saved values exist, calibration is needed (first time)
        if not saved_values:
            logging.info("No previous calibration values found. Calibration needed.")
            return True
        
        # Check if current readings are outside the saved range (with tolerance)
        saved_magXmin = saved_values.get('magXmin', 0)
        saved_magXmax = saved_values.get('magXmax', 0)
        saved_magYmin = saved_values.get('magYmin', 0)
        saved_magYmax = saved_values.get('magYmax', 0)
        saved_magZmin = saved_values.get('magZmin', 0)
        saved_magZmax = saved_values.get('magZmax', 0)
        
        outside_range = (
            MAGx < (saved_magXmin - self.TOLERANCE) or MAGx > (saved_magXmax + self.TOLERANCE) or
            MAGy < (saved_magYmin - self.TOLERANCE) or MAGy > (saved_magYmax + self.TOLERANCE) or
            MAGz < (saved_magZmin - self.TOLERANCE) or MAGz > (saved_magZmax + self.TOLERANCE)
        )
        
        if outside_range:
            logging.info("Values differ from saved calibration values. Calibration needed.")
            return True
        
        logging.info("Current values are within saved calibration range. Calibration not needed.")
        return False
    
    def _skip_initial_readings(self):
        """Discard the first few readings to stabilize the sensor and check if calibration is needed."""
        if not self.skip_initial_readings:
            return
        
        for _ in range(self.INITIAL_SKIP_READINGS):
            IMU.readMAGx()
            IMU.readMAGy()
            IMU.readMAGz()
        
        self.skip_initial_readings = False
        
        # Turn LED solid while checking if calibration is needed
        logging.info("Checking if calibration is needed...")
        self._turn_led_solid()
        
        # Read values after skip and check if calibration is needed
        MAGx = IMU.readMAGx()
        MAGy = IMU.readMAGy()
        MAGz = IMU.readMAGz()
        
        # Check if calibration is needed
        self.calibration_needed = self._check_if_calibration_needed(MAGx, MAGy, MAGz)
        
        # Handle LED based on calibration need
        if self.calibration_needed:
            logging.info("Starting calibration - LED will blink during calibration")
            self._start_led_blinking()
        else:
            logging.info("Calibration not needed. Exiting.")
            self._stop_led_blinking()
            sys.exit(0)
    
    def _update_min_max_values(self, MAGx, MAGy, MAGz):
        """Update min/max magnetometer values."""
        if MAGx > self.magXmax:
            self.magXmax = MAGx
        if MAGy > self.magYmax:
            self.magYmax = MAGy
        if MAGz > self.magZmax:
            self.magZmax = MAGz
        if MAGx < self.magXmin:
            self.magXmin = MAGx
        if MAGy < self.magYmin:
            self.magYmin = MAGy
        if MAGz < self.magZmin:
            self.magZmin = MAGz
    
    def run(self):
        """Run the calibration process."""
        # Initialize IMU
        IMU.detectIMU()
        IMU.initIMU()
        
        # Load previous values if available
        self._initialize_values()
        
        # Main calibration loop (only runs if calibration is needed)
        while True:
            try:
                # Skip initial readings on first iteration
                self._skip_initial_readings()
                
                # Read magnetometer values
                MAGx = IMU.readMAGx()
                MAGy = IMU.readMAGy()
                MAGz = IMU.readMAGz()
                
                # Update min/max values
                self._update_min_max_values(MAGx, MAGy, MAGz)
                
                # Check if values have changed
                self._check_values_changed()
                
                # Increment iteration counter
                self.iteration_counter += 1
                
                # Check if calibration is complete
                if self._check_calibration_complete():
                    sys.exit(0)
                
                # Log current values
                logging.debug(
                    "magXmin  %i  magYmin  %i  magZmin  %i  ## magXmax  %i  magYmax  %i  magZmax %i  "
                    "(iterations: %i, changes: %i)" % (
                        self.magXmin, self.magYmin, self.magZmin,
                        self.magXmax, self.magYmax, self.magZmax,
                        self.iteration_counter, self.change_counter
                    )
                )
                
                # Slow program down a bit, makes the output more readable
                time.sleep(self.LOOP_DELAY)
                
            except Exception as e:
                logging.error(f"Error in main loop: {e}")
                time.sleep(self.LOOP_DELAY)
                continue


def main():
    """Main entry point for the calibration script."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Calibrate IMU compass')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--save-path', type=str, default='IMU_values', 
                       help='Path where to save IMU calibration values (default: IMU_values)')
    
    def parse_led_gpio(value):
        """Parse LED GPIO argument, allowing None to disable LED."""
        if str(value).lower() == 'none':
            return None
        try:
            return int(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"LED GPIO must be an integer or 'None', got: {value}")
    
    parser.add_argument('--led-gpio', type=parse_led_gpio, default=21,
                       help='GPIO pin number for LED (default: 21, use --led-gpio None to disable)')
    args = parser.parse_args()
    
    led_gpio = args.led_gpio
    
    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(levelname)s: %(message)s'
    )
    
    # Create and run calibrator
    calibrator = IMUCalibrator(save_path=args.save_path, led_gpio=led_gpio)
    calibrator.run()


if __name__ == '__main__':
    main()
