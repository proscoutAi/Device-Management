import math
from threading import Thread
import threading
import smbus
bus = smbus.SMBus(1)
import RPi.GPIO as GPIO

from LSM6DSL import *
from MMC5983MA import *
import time
import sys
import board
import busio
from adafruit_bmp3xx import BMP3XX_I2C

# Import flow meter control functions
try:
    from flow_meter import start_flow_monitoring, stop_flow_monitoring, is_flow_monitoring_active
    FLOW_METER_AVAILABLE = True
except ImportError:
    print("Flow meter module not available")
    FLOW_METER_AVAILABLE = False

#for wake up
LSM6DSL_WAKE_UP_THS = 0x5B
LSM6DSL_WAKE_UP_DUR = 0x5C  
LSM6DSL_WAKE_UP_SRC = 0x1B
LSM6DSL_INT1_CTRL = 0x0D
LSM6DSL_TAP_CFG = 0x58

RAD_TO_DEG = 57.29578
M_PI = 3.14159265358979323846
G_GAIN = 0.070  # [deg/s/LSB]  If you change the dps for gyro, you need to update this value accordingly
AA =  0.40      # Complementary filter constant
mRes = 1.0/16384.0
MMC5983MA_offset = 131072.0
acc_sensitivity = 0.244 / 1000  # 0.000244 g per LSB
gyro_sensativity = 0.07 #°/s per LSB

# NEW CALIBRATION VALUES FROM YOUR CALIBRATION RUN
magXmin = 124740
magYmin = 127376
magZmin = 124972
magXmax = 137005
magYmax = 136892
magZmax = 138556

# Hard iron offsets
offset_x = 130872.5
offset_y = 132134.0
offset_z = 131764.0

# Soft iron scales
scale_x = 0.961136023916293
scale_y = 1.2387908084629398
scale_z = 0.86781016882607

MOTION_PIN = 18      # Connect to LSM6DSL INT1
INACTIVITY_PIN = 19  # Connect to LSM6DSL INT2
SLEEP_TIMEOUT = 30 * 60  # 30 minutes in seconds

imu_buffer = []
lock = threading.Lock()

class IMUManager:
    def __init__(self,imu_rate_per_second):
        
        self.detectIMU()
        
        self.last_motion_time = time.time()
        self.is_active = False
        self.sleep_timer = None
        self.stop_event = threading.Event()  # ADDED: Missing stop event
        self.high_freq_mode = False  # ADDED: Track current mode
        
        # Setup GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(MOTION_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(INACTIVITY_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        # Setup interrupt handlers
        GPIO.add_event_detect(MOTION_PIN, GPIO.FALLING, 
                            callback=self.motion_detected_callback, bouncetime=300)
        GPIO.add_event_detect(INACTIVITY_PIN, GPIO.FALLING,
                            callback=self.inactivity_detected_callback, bouncetime=300)  # FIXED: Better name
        
        # Start in WAKE-UP mode (low power)
        self.configure_wake_mode()

        #Enable compass, Continuous measurement mode, 100Hz
        self.writeByte(MMC5983MA_ADDRESS,MMC5983MA_CONTROL_0,0b00001000)     #"deGauss" magnetometer
        time.sleep(0.2)
        self.writeByte(MMC5983MA_ADDRESS,MMC5983MA_CONTROL_1,0b10000000)     #soft reset
        time.sleep(0.2)
        self.writeByte(MMC5983MA_ADDRESS,MMC5983MA_CONTROL_0,0b00100100)     #Enable auto reset
        self.writeByte(MMC5983MA_ADDRESS,MMC5983MA_CONTROL_1,0b00000000)     #Filter bandwdith 100Hz (16 bit mode)
        self.writeByte(MMC5983MA_ADDRESS,MMC5983MA_CONTROL_2,0b10001101)     #Continous mode at 100Hz
        i2c = busio.I2C(board.SCL, board.SDA)
        self.barometer_sensor = BMP3XX_I2C(i2c, address=0x77)
        self.imu_rate_per_second = 1/imu_rate_per_second
        
        self.imu_data = {
            'GYRx': 0.0,
            'GYRy': 0.0,
            'GYRz': 0.0,
            'MAGx': 0.0,
            'MAGy': 0.0,
            'MAGz': 0.0,
            'ACCx': 0.0,
            'ACCy': 0.0,
            'ACCz': 0.0,
            'heading_compensated_deg':0.0,
            'Temperature' : 0.0,
            'Pressure' : 0.0,
            'ACCx_mg_unit':0.0,
            'ACCy_mg_unit':0.0,
            'ACCz_mg_unit':0.0,
            'GYRx_dps':0.0,
            'GYRy_dps':0.0,
            'GYRz_dps':0.0    
        }
        
        self.thread = None
        print("IMU Manager initialized in wake-on-motion mode")
        
    def writeByte(self,device_address,register,value):
       bus.write_byte_data(device_address, register, value)
       
    def readByte(self, device_address, register):  # ADDED: Missing method
        return bus.read_byte_data(device_address, register)
       
    def configure_wake_mode(self):
        """Configure for low-power wake-on-motion"""
        # Low power accelerometer settings for wake detection
        self.writeByte(LSM6DSL_ADDRESS,LSM6DSL_CTRL1_XL,0b00010000)  # 12.5Hz, ±2g
        
        # Wake-up threshold
        self.writeByte(LSM6DSL_ADDRESS,LSM6DSL_WAKE_UP_THS,0x08)
        
        # Wake-up duration  
        self.writeByte(LSM6DSL_ADDRESS,LSM6DSL_WAKE_UP_DUR,0x01)
        
        # Enable wake-up interrupt on INT1
        self.writeByte(LSM6DSL_ADDRESS,LSM6DSL_INT1_CTRL,0x20)
        
        # Enable wake-up detection
        self.writeByte(LSM6DSL_ADDRESS,LSM6DSL_TAP_CFG,0x80)
        
        self.high_freq_mode = False
        print("Wake-on-motion configured")
    
    def configure_high_freq_mode(self):
        """Switch to high-frequency data collection mode"""
        # Your original high-frequency settings
        self.writeByte(LSM6DSL_ADDRESS,LSM6DSL_CTRL1_XL,0b10011111)  # 3.33 kHz, +/- 8g 
        self.writeByte(LSM6DSL_ADDRESS,LSM6DSL_CTRL8_XL,0b11001000)  # Low pass filter
        self.writeByte(LSM6DSL_ADDRESS,LSM6DSL_CTRL3_C,0b01000100)   # Block data update
        
        # Initialize gyroscope
        self.writeByte(LSM6DSL_ADDRESS,LSM6DSL_CTRL2_G,0b10011100)   # 3.3 kHz, 2000 dps
        
        self.high_freq_mode = True
        print("High-frequency mode configured")
        
    def motion_detected_callback(self, channel):
        """Called when motion is detected"""
        try:
            # Clear wake-up interrupt
            wake_src = self.readByte(LSM6DSL_ADDRESS, LSM6DSL_WAKE_UP_SRC)
            
            # Ignore if already active
            if self.is_active:
                print("Motion detected but already active")
                return
            
            print("Motion detected! Starting high-frequency data collection...")
            
            # Update state
            self.last_motion_time = time.time()
            self.is_active = True
            self.sleep_timer = None  # Reset sleep timer
            
            # Switch to high-frequency mode
            self.configure_high_freq_mode()
            
            # Start flow meter monitoring if available
            if FLOW_METER_AVAILABLE:
                if start_flow_monitoring():
                    print("Flow meter monitoring started")
                else:
                    print("Failed to start flow meter monitoring")
            
            # Start IMU data collection thread
            self.start_imu_collection()
            
        except Exception as e:
            print(f"Error in motion detection: {e}")
    
    def inactivity_detected_callback(self, channel):  # FIXED: Renamed from switch_back_to_wake_mode
        """Called when inactivity is detected"""
        print("Inactivity detected by hardware")
        # This can be used for additional inactivity logic if needed
        
    def start_imu_collection(self):
        """Start IMU data collection thread"""
        # Stop existing thread if running
        if self.thread and self.thread.is_alive():
            self.stop_imu_collection()
        
        # Start new thread
        self.stop_event.clear()
        self.thread = Thread(target=self.update_imu)
        self.thread.start()
        print("IMU data collection started")
        
    def stop_imu_collection(self):
        """Stop IMU data collection thread"""
        if self.thread and self.thread.is_alive():
            print("Stopping IMU collection...")
            self.stop_event.set()
            self.thread.join(timeout=2)
            
            if self.thread.is_alive():
                print("Warning: Thread didn't stop gracefully")
            else:
                print("IMU collection stopped")
    
    def check_for_sleep(self):
        """Check if we should enter sleep mode due to inactivity"""
        if not self.is_active:
            return
            
        # Check if we've been inactive for too long
        if self.sleep_timer is None:
            self.sleep_timer = time.time()
        else:
            time_since_last_check = time.time() - self.sleep_timer
            if time_since_last_check >= SLEEP_TIMEOUT:
                self.enter_sleep_mode()
    
    def enter_sleep_mode(self):
        """Enter sleep mode after inactivity"""
        print("Entering sleep mode due to inactivity...")
        
        # Stop flow meter monitoring if available
        if FLOW_METER_AVAILABLE:
            stop_flow_monitoring()
            print("Flow meter monitoring stopped")
        
        # Stop data collection
        self.stop_imu_collection()
        
        # Switch back to wake mode
        self.configure_wake_mode()
        
        # Reset state
        self.is_active = False
        self.sleep_timer = None
        
        print("System in sleep mode - waiting for motion...")
            
    def detectIMU(self):
        try:
            #Check for OzzMaker LTE IMU ALT (LSM6DSL and MMC5983MA)
            #If no LSM6DSL or MMC5983MA is connected, there will be an I2C bus error and the program will exit.
            #This section of code stops this from happening.
            LSM6DSL_WHO_AM_I_response = (bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_WHO_AM_I))
            MMC5983MA_WHO_AM_I_response = (bus.read_byte_data(MMC5983MA_ADDRESS,MMC5983MA_WHO_AM_I ))

        except IOError as f:
            print(f'{time.ctime(time.time())}:OzzMaker LTE IMU ALT not found')        #need to do something here, so we just print a space
            sys.exit(1)
        else:
            if (LSM6DSL_WHO_AM_I_response == 0x6A) and (MMC5983MA_WHO_AM_I_response == 0x30):
                print(f"{time.ctime(time.time())}:Found OzzMaker LTE IMU ALT (LSM6DSL and MMC5983MA)")

        time.sleep(1)
        
    def readACCx(self):
        acc_l = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTX_L_XL)
        acc_h = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTX_H_XL)
        acc_combined = (acc_l | acc_h <<8)
        acc_combined = acc_combined  if acc_combined < 32768 else acc_combined - 65536
        self.imu_data['ACCx'] = acc_combined
        self.imu_data['ACCx_mg_unit'] = acc_combined *acc_sensitivity

    def readACCy(self):
        acc_l = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTY_L_XL)
        acc_h = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTY_H_XL)
        acc_combined = (acc_l | acc_h <<8)
        acc_combined = acc_combined  if acc_combined < 32768 else acc_combined - 65536
        self.imu_data['ACCy'] = acc_combined
        self.imu_data['ACCy_mg_unit'] = acc_combined *acc_sensitivity

    def readACCz(self):
        acc_l = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTZ_L_XL)
        acc_h = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTZ_H_XL)
        acc_combined = (acc_l | acc_h <<8)
        acc_combined = acc_combined  if acc_combined < 32768 else acc_combined - 65536
        self.imu_data['ACCz'] = acc_combined
        self.imu_data['ACCz_g_unit'] = acc_combined *acc_sensitivity

    def readGYRx(self):
        gyr_l = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTX_L_G)
        gyr_h = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTX_H_G)
        gyr_combined = (gyr_l | gyr_h <<8)
        gyr_combined = gyr_combined  if gyr_combined < 32768 else gyr_combined - 65536
        self.imu_data['GYRx'] = gyr_combined
        self.imu_data['GYRx_dps'] = gyr_combined *gyro_sensativity

    def readGYRy(self):
        gyr_l = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTY_L_G)
        gyr_h = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTY_H_G)
        gyr_combined = (gyr_l | gyr_h <<8)
        gyr_combined =  gyr_combined if gyr_combined < 32768 else gyr_combined - 65536
        self.imu_data['GYRy'] = gyr_combined
        self.imu_data['GYRy_dps'] = gyr_combined *gyro_sensativity

    def readGYRz(self):
        gyr_l = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTZ_L_G)
        gyr_h = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTZ_H_G)
        gyr_combined = (gyr_l | gyr_h <<8)
        gyr_combined = gyr_combined  if gyr_combined < 32768 else gyr_combined - 65536
        self.imu_data['GYRz'] = gyr_combined
        self.imu_data['GYRz_dps'] = gyr_combined *gyro_sensativity

    def readMAGx(self):
        mag_l = bus.read_byte_data(MMC5983MA_ADDRESS, MMC5983MA_XOUT_0)
        mag_h = bus.read_byte_data(MMC5983MA_ADDRESS, MMC5983MA_XOUT_1)
        mag_xyz = bus.read_byte_data(MMC5983MA_ADDRESS,MMC5983MA_XYZOUT_2)
        
        # Get raw 18-bit value
        MAGx_raw = mag_l << 10 | mag_h << 2 | (mag_xyz & 0b11000000) >> 6
        
        # Apply hard iron correction (remove offset)
        MAGx_corrected = MAGx_raw - offset_x
        
        # Apply soft iron correction (scale normalization)
        MAGx_scaled = MAGx_corrected * scale_x
        
        # Convert to final units (gauss or tesla)
        MAGx_final = MAGx_scaled * (mRes)
        
        self.imu_data['MAGx'] = MAGx_final

    def readMAGy(self):
        mag_l = bus.read_byte_data(MMC5983MA_ADDRESS, MMC5983MA_YOUT_0)
        mag_h = bus.read_byte_data(MMC5983MA_ADDRESS, MMC5983MA_YOUT_1)
        mag_xyz = bus.read_byte_data(MMC5983MA_ADDRESS,MMC5983MA_XYZOUT_2)
        
        # Get raw 18-bit value
        MAGy_raw = mag_l << 10 | mag_h <<2 | (mag_xyz & 0b00110000) >> 4
        
        # Apply hard iron correction (remove offset)
        MAGy_corrected = MAGy_raw - offset_y
        
        # Apply soft iron correction (scale normalization)
        MAGy_scaled = MAGy_corrected * scale_y
        
        # Convert to final units (gauss or tesla)
        MAGy_final = MAGy_scaled * (mRes)
        
        self.imu_data['MAGy'] = MAGy_final

    def readMAGz(self):
        mag_l = bus.read_byte_data(MMC5983MA_ADDRESS, MMC5983MA_ZOUT_0)
        mag_h = bus.read_byte_data(MMC5983MA_ADDRESS, MMC5983MA_ZOUT_1)
        mag_xyz = bus.read_byte_data(MMC5983MA_ADDRESS,MMC5983MA_XYZOUT_2)
        
        # Get raw 18-bit value
        MAGz_raw = mag_l << 10 | mag_h <<2 | (mag_xyz & 0b00001100) >> 2
        
        # Apply hard iron correction (remove offset)
        MAGz_corrected = MAGz_raw - offset_z
        
        # Apply soft iron correction (scale normalization)
        MAGz_scaled = MAGz_corrected * scale_z
        
        # Convert to final units (gauss or tesla)
        MAGz_final = MAGz_scaled * (mRes)
        
        self.imu_data['MAGz'] = MAGz_final
    
    def read_temperature(self):
        self.imu_data['Temperature'] = self.barometer_sensor.temperature
        self.imu_data['Pressure'] = self.barometer_sensor.pressure
        
    def update_imu(self):
        """FIXED: Added stop condition"""
        while not self.stop_event.is_set():  # Check for stop signal
            try:
                self.readACCx()
                self.readACCy()
                self.readACCz()
                self.readGYRx()
                self.readGYRy()
                self.readGYRz()
                self.readMAGx()
                self.readMAGy()
                self.readMAGz()
                self.update_tilt_compensated_heading()
                self.read_temperature()
                
                # Add to buffer thread-safely
                with lock:
                    imu_buffer.append(self.imu_data.copy())
                
                # Check for sleep periodically
                self.check_for_sleep()
                    
                time.sleep(self.imu_rate_per_second)
                
            except Exception as e:
                print(f"Error in update_imu: {e}")
                break
                
        print("update_imu thread stopped")
    
    def get_imu_buffer_and_reset(self):
        global imu_buffer
        with lock:
            batch = imu_buffer.copy()
            imu_buffer = []
            return batch

    def get_heading(self):
        """Calculate heading with tilt compensation"""
        data = self.get_imu()
        
        # Simple heading calculation (works best when device is level)
        heading_rad = math.atan2(data['MAGy'], data['MAGx'])
        heading_deg = heading_rad * (180.0/math.pi)
        
        # Normalize to 0-360 degrees
        if heading_deg < 0:
            heading_deg += 360
            
        return heading_deg

    def update_tilt_compensated_heading(self):
        try:
            """Calculate heading with tilt compensation using accelerometer"""
            data = self.imu_data
            
            # Normalize accelerometer readings
            acc_x = data['ACCx']
            acc_y = data['ACCy'] 
            acc_z = data['ACCz']
            
            # Calculate roll and pitch from accelerometer
            roll = math.atan2(acc_y, acc_z)
            pitch = math.atan2(-acc_x, math.sqrt(acc_y*acc_y + acc_z*acc_z))
            
            # Tilt compensated magnetometer readings
            mag_x = data['MAGx']
            mag_y = data['MAGy']
            mag_z = data['MAGz']
            
            # Apply tilt compensation
            mag_x_comp = mag_x * math.cos(pitch) + mag_z * math.sin(pitch)
            mag_y_comp = mag_x * math.sin(roll) * math.sin(pitch) + mag_y * math.cos(roll) - mag_z * math.sin(roll) * math.cos(pitch)
            
            # Calculate heading
            heading_rad = math.atan2(mag_y_comp, mag_x_comp)
            heading_deg = heading_rad * (180.0/math.pi)
            
            # Normalize to 0-360 degrees
            if heading_deg < 0:
                heading_deg += 360
            self.imu_data['heading_compensated_deg'] = heading_deg
                
            return heading_deg
        except Exception as e:
            print(f"{time.ctime(time.time())}:IMU Manager: Error getting compensated heading: {e}")
            return None
    
    def cleanup(self):
        """Clean up resources when shutting down"""
        print("Cleaning up IMU Manager...")
        
        # Stop flow meter monitoring
        if FLOW_METER_AVAILABLE:
            stop_flow_monitoring()
            print("Flow meter monitoring stopped during cleanup")
        
        self.stop_imu_collection()
        GPIO.cleanup()
        print("IMU Manager cleanup complete")