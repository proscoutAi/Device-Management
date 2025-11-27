import math
import threading
from threading import Thread

import smbus

bus = smbus.SMBus(1)

import sys
import time

import calibrate.IMU_calibration as imu_calibration
from LSM6DSL import *
from MMC5983MA import *

RAD_TO_DEG = 57.29578
M_PI = 3.14159265358979323846
G_GAIN = 0.070  # [deg/s/LSB]  If you change the dps for gyro, you need to update this value accordingly
AA =  0.40      # Complementary filter constant
mRes = 1.0/16384.0
MMC5983MA_offset = 131072.0
acc_sensitivity = 0.244 / 1000  # 0.000244 g per LSB
gyro_sensativity = 0.07 #°/s per LSB



imu_buffer = []
lock = threading.Lock()

class IMUManager:
    def __init__(self,imu_rate_per_second):
        
        IMUCalibrator = imu_calibration.IMUCalibrator()
        imu_values = IMUCalibrator.run()
                
        # NEW CALIBRATION VALUES FROM YOUR CALIBRATION RUN
        magXmin = imu_values.get('magXmin', 124740)
        magYmin = imu_values.get('magYmin', 127376)
        magZmin = imu_values.get('magZmin', 124972)
        magXmax = imu_values.get('magXmax', 137005)
        magYmax = imu_values.get('magYmax', 136892)
        magZmax = imu_values.get('magZmax', 138556)

        # Hard iron offsets (center point)
        self.offset_x = (magXmax + magXmin) / 2.0
        self.offset_y = (magYmax + magYmin) / 2.0
        self.offset_z = (magZmax + magZmin) / 2.0

        # Soft iron scales (normalization)
        # Find the average range
        avg_range = ((magXmax - magXmin) + (magYmax - magYmin) + (magZmax - magZmin)) / 3.0

        self.scale_x = avg_range / (magXmax - magXmin)
        self.scale_y = avg_range / (magYmax - magYmin)
        self.scale_z = avg_range / (magZmax - magZmin)
        
        self.detectIMU()
         #initialise the accelerometer
        self.writeByte(LSM6DSL_ADDRESS,LSM6DSL_CTRL1_XL,0b10011111)           #ODR 3.33 kHz, +/- 8g , BW = 400hz
        self.writeByte(LSM6DSL_ADDRESS,LSM6DSL_CTRL8_XL,0b11001000)           #Low pass filter enabled, BW9, composite filter
        self.writeByte(LSM6DSL_ADDRESS,LSM6DSL_CTRL3_C,0b01000100)            #Enable Block Data update, increment during multi byte read

        #initialise the gyroscope
        self.writeByte(LSM6DSL_ADDRESS,LSM6DSL_CTRL2_G,0b10011100)            #ODR 3.3 kHz, 2000 dps

        #Enable compass, Continuous measurement mode, 100Hz
        self.writeByte(MMC5983MA_ADDRESS,MMC5983MA_CONTROL_0,0b00001000)     #"deGauss" magnetometer
        time.sleep(0.2)
        self.writeByte(MMC5983MA_ADDRESS,MMC5983MA_CONTROL_1,0b10000000)     #soft reset
        time.sleep(0.2)
        self.writeByte(MMC5983MA_ADDRESS,MMC5983MA_CONTROL_0,0b00100100)     #Enable auto reset
        self.writeByte(MMC5983MA_ADDRESS,MMC5983MA_CONTROL_1,0b00000000)     #Filter bandwdith 100Hz (16 bit mode)
        self.writeByte(MMC5983MA_ADDRESS,MMC5983MA_CONTROL_2,0b10001101)     #Continous mode at 100Hz
        #i2c = busio.I2C(board.SCL, board.SDA)
        #self.barometer_sensor = BMP3XX_I2C(i2c, address=0x77)
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
        
        
        self.thread = Thread(target=self.update_imu)
        self.thread.start()
        
    def writeByte(self,device_address,register,value):
       bus.write_byte_data(device_address, register, value)
        
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
        try:
            with lock: # Prevents other I2C traffic from interrupting
                acc_l = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTX_L_XL)
                acc_h = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTX_H_XL)
                acc_combined = (acc_l | acc_h <<8)
                acc_combined = acc_combined  if acc_combined < 32768 else acc_combined - 65536
                self.imu_data['ACCx'] = acc_combined
                self.imu_data['ACCx_mg_unit'] = acc_combined *acc_sensitivity
        except OSError as e:
           print(f"I2C Communication Error: {e}")
           print(f"Check connections and address (0x{MMC5983MA_ADDRESS:02X})")
        except Exception as e:
           print(f"Unexpected error: {type(e).__name__}: {e}")

    def readACCy(self):
        try:
            with lock: # Prevents other I2C traffic from interrupting
                acc_l = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTY_L_XL)
                acc_h = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTY_H_XL)
                acc_combined = (acc_l | acc_h <<8)
                acc_combined = acc_combined  if acc_combined < 32768 else acc_combined - 65536
                self.imu_data['ACCy'] = acc_combined
                self.imu_data['ACCy_mg_unit'] = acc_combined *acc_sensitivity
        except OSError as e:
           print(f"I2C Communication Error: {e}")
           print(f"Check connections and address (0x{MMC5983MA_ADDRESS:02X})")
        except Exception as e:
           print(f"Unexpected error: {type(e).__name__}: {e}")

    def readACCz(self):
        try:
            with lock: # Prevents other I2C traffic from interrupting
                acc_l = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTZ_L_XL)
                acc_h = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTZ_H_XL)
                acc_combined = (acc_l | acc_h <<8)
                acc_combined = acc_combined  if acc_combined < 32768 else acc_combined - 65536
                self.imu_data['ACCz'] = acc_combined
                self.imu_data['ACCz_g_unit'] = acc_combined *acc_sensitivity
        except OSError as e:
           print(f"I2C Communication Error: {e}")
           print(f"Check connections and address (0x{MMC5983MA_ADDRESS:02X})")
        except Exception as e:
           print(f"Unexpected error: {type(e).__name__}: {e}")

    def readGYRx(self):
        try:
            with lock: # Prevents other I2C traffic from interrupting
                gyr_l = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTX_L_G)
                gyr_h = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTX_H_G)
                gyr_combined = (gyr_l | gyr_h <<8)
                gyr_combined = gyr_combined  if gyr_combined < 32768 else gyr_combined - 65536
                self.imu_data['GYRx'] = gyr_combined
                self.imu_data['GYRx_dps'] = gyr_combined *gyro_sensativity
        except OSError as e:
           print(f"I2C Communication Error: {e}")
           print(f"Check connections and address (0x{MMC5983MA_ADDRESS:02X})")
        except Exception as e:
           print(f"Unexpected error: {type(e).__name__}: {e}")

    def readGYRy(self):
      try:
        with lock: # Prevents other I2C traffic from interrupting
            gyr_l = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTY_L_G)
            gyr_h = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTY_H_G)
            gyr_combined = (gyr_l | gyr_h <<8)
            gyr_combined =  gyr_combined if gyr_combined < 32768 else gyr_combined - 65536
            self.imu_data['GYRy'] = gyr_combined
            self.imu_data['GYRy_dps'] = gyr_combined *gyro_sensativity
      except OSError as e:
           print(f"I2C Communication Error: {e}")
           print(f"Check connections and address (0x{MMC5983MA_ADDRESS:02X})")
      except Exception as e:
           print(f"Unexpected error: {type(e).__name__}: {e}")

    def readGYRz(self):
        try:
            with lock: # Prevents other I2C traffic from interrupting
                gyr_l = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTZ_L_G)
                gyr_h = bus.read_byte_data(LSM6DSL_ADDRESS, LSM6DSL_OUTZ_H_G)
                gyr_combined = (gyr_l | gyr_h <<8)
                gyr_combined = gyr_combined  if gyr_combined < 32768 else gyr_combined - 65536
                self.imu_data['GYRz'] = gyr_combined
                self.imu_data['GYRz_dps'] = gyr_combined *gyro_sensativity
        except OSError as e:
           print(f"I2C Communication Error: {e}")
           print(f"Check connections and address (0x{MMC5983MA_ADDRESS:02X})")
        except Exception as e:
           print(f"Unexpected error: {type(e).__name__}: {e}")       

    def readMAGx(self):
        try:
            with lock: # Prevents other I2C traffic from interrupting
                mag_l = bus.read_byte_data(MMC5983MA_ADDRESS, MMC5983MA_XOUT_0)
                mag_h = bus.read_byte_data(MMC5983MA_ADDRESS, MMC5983MA_XOUT_1)
                mag_xyz = bus.read_byte_data(MMC5983MA_ADDRESS,MMC5983MA_XYZOUT_2)
                
                # Get raw 18-bit value
                MAGx_raw = mag_l << 10 | mag_h << 2 | (mag_xyz & 0b11000000) >> 6
                
                # Apply hard iron correction (remove offset)
                MAGx_corrected = MAGx_raw - self.offset_x
                
                # Apply soft iron correction (scale normalization)
                MAGx_scaled = MAGx_corrected * self.scale_x
                
                # Convert to final units (gauss or tesla)
                MAGx_final = MAGx_scaled * (mRes)
                
                self.imu_data['MAGx'] = MAGx_final
        except OSError as e:
           print(f"I2C Communication Error: {e}")
           print(f"Check connections and address (0x{MMC5983MA_ADDRESS:02X})")
        except Exception as e:
           print(f"Unexpected error: {type(e).__name__}: {e}")

    def readMAGy(self):
        try:
            with lock: # Prevents other I2C traffic from interrupting
                mag_l = bus.read_byte_data(MMC5983MA_ADDRESS, MMC5983MA_YOUT_0)
                mag_h = bus.read_byte_data(MMC5983MA_ADDRESS, MMC5983MA_YOUT_1)
                mag_xyz = bus.read_byte_data(MMC5983MA_ADDRESS,MMC5983MA_XYZOUT_2)
                
                # Get raw 18-bit value
                MAGy_raw = mag_l << 10 | mag_h <<2 | (mag_xyz & 0b00110000) >> 4
                
                # Apply hard iron correction (remove offset)
                MAGy_corrected = MAGy_raw - self.offset_y
                
                # Apply soft iron correction (scale normalization)
                MAGy_scaled = MAGy_corrected * self.scale_y
                
                # Convert to final units (gauss or tesla)
                MAGy_final = MAGy_scaled * (mRes)
                
                self.imu_data['MAGy'] = MAGy_final
        except OSError as e:
           print(f"I2C Communication Error: {e}")
           print(f"Check connections and address (0x{MMC5983MA_ADDRESS:02X})")
        except Exception as e:
           print(f"Unexpected error: {type(e).__name__}: {e}")

    def readMAGz(self):
        try:
            with lock: # Prevents other I2C traffic from interrupting
                mag_l = bus.read_byte_data(MMC5983MA_ADDRESS, MMC5983MA_ZOUT_0)
                mag_h = bus.read_byte_data(MMC5983MA_ADDRESS, MMC5983MA_ZOUT_1)
                mag_xyz = bus.read_byte_data(MMC5983MA_ADDRESS,MMC5983MA_XYZOUT_2)
                
                # Get raw 18-bit value
                MAGz_raw = mag_l << 10 | mag_h <<2 | (mag_xyz & 0b00001100) >> 2
                
                # Apply hard iron correction (remove offset)
                MAGz_corrected = MAGz_raw - self.offset_z
                
                # Apply soft iron correction (scale normalization)
                MAGz_scaled = MAGz_corrected * self.scale_z
                
                # Convert to final units (gauss or tesla)
                MAGz_final = MAGz_scaled * (mRes)
                
                self.imu_data['MAGz'] = MAGz_final
        except OSError as e:
           print(f"I2C Communication Error: {e}")
           print(f"Check connections and address (0x{MMC5983MA_ADDRESS:02X})")
        except Exception as e:
           print(f"Unexpected error: {type(e).__name__}: {e}")
        
    def read_temperature(self):
        self.imu_data['Temperature'] = self.barometer_sensor.temperature
        self.imu_data['Pressure'] = self.barometer_sensor.pressure
        
    
    def update_imu(self):
        while True:
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
            #self.read_temperature()
            imu_buffer.append (self.imu_data.copy())
            time.sleep(self.imu_rate_per_second)
    
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
            



'''
# Test the updated calibration
if __name__ == "__main__":
    print("Testing updated magnetometer calibration...")
    print("Rotate the device to test heading changes")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            data = get_imu_data()
            heading = get_heading()
            tilt_heading = get_tilt_compensated_heading()
            
            print(f"MAG: X={data['MAGx']:.3f}, Y={data['MAGy']:.3f}, Z={data['MAGz']:.3f}")
            print(f"Heading: {heading:.1f}° | Tilt compensated: {tilt_heading:.1f}°")
            print("-" * 50)
            
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\nTest stopped by user")

'''