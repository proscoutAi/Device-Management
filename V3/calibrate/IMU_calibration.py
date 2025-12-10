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

from button_led_manager import ButtonLEDManager, LEDColor

from . import IMU


class IMUCalibrator:
    """Calibrates IMU compass by tracking min/max magnetometer values."""
    
    # Calibration constants
    ITERATION_THRESHOLD = 300
    led_manager = ButtonLEDManager()
    # Calibration constants
    ITERATION_THRESHOLD = 150
    MAX_CHANGES_ALLOWED = 5
    INITIAL_SKIP_READINGS = 10
    TOLERANCE = 100
    LOOP_DELAY = 0.03
    
    def __init__(self, save_path='IMU_values'):
        """
        Initialize the IMU calibrator.
        
        Args:
            save_path (str): Path where to save the IMU calibration values
        """
        self.save_path = save_path
        
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
    
    def get_current_calibration_values(self):
        """
        Get current calibration values from memory (not from file).
        
        Returns:
            dict: Dictionary containing current calibration values with keys:
                - 'magXmin', 'magYmin', 'magZmin'
                - 'magXmax', 'magYmax', 'magZmax'
        """
        return {
            'magXmin': self.magXmin,
            'magYmin': self.magYmin,
            'magZmin': self.magZmin,
            'magXmax': self.magXmax,
            'magYmax': self.magYmax,
            'magZmax': self.magZmax
        }
    
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
            print(f"{time.ctime(time.time())}:Calibration values saved to {self.save_path}")
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
        
        self.led_manager.turn_off()
        sys.exit(130)  # 130 is standard exit code for ctrl-c
    
    def _initialize_values(self):
        """Initialize min/max values from saved file or use defaults."""
        saved_values = self._load_imu_values()
        
        if saved_values:
            print(f"{time.ctime(time.time())}:Loaded previous calibration values from file")
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
                if self._save_imu_values():
                    print(f"{time.ctime(time.time())}:Calibration complete! Values saved.")
                    print(f"{time.ctime(time.time())}:Completed {self.iteration_counter} iterations with {self.change_counter} changes.")
                    self.led_manager.turn_off()
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
            print(f"{time.ctime(time.time())}:No previous calibration values found. Calibration needed.")
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
            print(f"{time.ctime(time.time())}:Values differ from saved calibration values. Calibration needed.")
            return True
        
        print(f"{time.ctime(time.time())}:Current values are within saved calibration range. Calibration not needed.")
        return False
    
    def _skip_initial_readings(self):
        """
        Discard the first few readings to stabilize the sensor and check if calibration is needed.
        
        Returns:
            False if calibration is not needed, None otherwise (continues with calibration).
        """
        if not self.skip_initial_readings:
            return None
        
        for _ in range(self.INITIAL_SKIP_READINGS):
            IMU.readMAGx()
            IMU.readMAGy()
            IMU.readMAGz()
        
        self.skip_initial_readings = False
        
        # Turn LED solid while checking if calibration is needed
        print(f"{time.ctime(time.time())}:Checking if calibration is needed...")
        
        # Read values after skip and check if calibration is needed
        MAGx = IMU.readMAGx()
        MAGy = IMU.readMAGy()
        MAGz = IMU.readMAGz()
        
        # Check if calibration is needed
        self.calibration_needed = self._check_if_calibration_needed(MAGx, MAGy, MAGz)
        
        # Handle LED based on calibration need
        if self.calibration_needed:
            print(f"{time.ctime(time.time())}:Starting calibration - LED will blink during calibration")
            self.led_manager.blink(LEDColor.GREEN, 500)
            return None  # Continue with calibration
        else:
            print(f"{time.ctime(time.time())}:Calibration not needed.")
            return False  # Signal that calibration was not needed
    
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
        """
        Run the calibration process.
        
        Returns:
            dict: Dictionary containing calibration values with keys:
                - 'magXmin', 'magYmin', 'magZmin'
                - 'magXmax', 'magYmax', 'magZmax'
            Returns None if calibration was not needed (values already good).
        """
        print(f"{time.ctime(time.time())}:Starting IMU calibration...")
        # Initialize IMU
        IMU.detectIMU()
        IMU.initIMU()
        
        # Load previous values if available
        self._initialize_values()
        
        # Main calibration loop (only runs if calibration is needed)
        while True:
            try:
                # Skip initial readings on first iteration
                calibration_not_needed = self._skip_initial_readings()
                
                # If calibration is not needed, return existing values
                if calibration_not_needed is False:
                    return self._load_imu_values()
                
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
                    # Return the calibration values
                    return self.get_current_calibration_values()
                
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
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(levelname)s: %(message)s'
    )
    
    # Create and run calibrator
    calibrator = IMUCalibrator(save_path=args.save_path)
    calibrator.run()


if __name__ == '__main__':
    main()
