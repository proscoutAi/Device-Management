from datetime import datetime
from threading import Thread
from time import sleep
import time

from camera import Camera
from upload import CloudFunctionClient 
from concurrent.futures import ThreadPoolExecutor
from flow_meter import get_counter_and_reset,cleanup,setup_flow_meter
import configparser
import os
from gps_manager import get_gps_data
from IMU_manager import IMUManager
import sys
import gc
import socket


sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# read input folder from config file
if not os.path.exists('config.ini'):
    raise ValueError("Configuration file 'config.ini' not found. Please create it.")
config = configparser.ConfigParser()
config.read('config.ini')

sleep_interval = config.getint('Setup', 'sleep_interval')
camera_connected = config.getboolean('Setup', 'camera')
flow_meter_connected = config.getboolean('Setup', 'flow_meter')
production = config.getboolean('Setup', 'production')
url_key = 'cloud_function_url_prod' if production else 'cloud_function_url_stg'
cloud_function_url = config.get('Setup', url_key)
print(f"working cloud url is:{cloud_function_url}")
batch_size = config.getint('Setup', 'batch_size')
imu_rate_per_second = config.getint('Setup', 'imu_rate_per_second')
interval_in_hours = sleep_interval/3600
flow_meter_pulses_per_litter = config.getint('Setup', 'flow_meter_pulses_per_litter')

executor = ThreadPoolExecutor(max_workers=5)

# Read the unique identifier (UUID or MAC address)
with open("/home/proscout/ProScout-master/device-manager/device_id.txt", "r") as f:
      client_device_id = f.read().strip()

time_format = '%Y-%m-%d_%H-%M-%S'



class Session:
    """A class to represent a session of image capture"""


    def __init__(self, camera_index: int = 0):
        """
        @param camera_index: The index of the camera device to use
        @param interval: The interval in seconds between each image capture
        """

        self.running = False
        self.start_time = None
        self.interval = sleep_interval
        self.camera_interval = sleep_interval//5 #this is the floor of the interval of snapping an image.
        self.camera_index = camera_index
        self.camera = None
        self.thread = None
        self.upload_threads = []
        self.upload_class = CloudFunctionClient(cloud_function_url,client_device_id,sleep_interval)
        self.batch_payload = []
        self.imu_manager = None
        
    
    def flash_batch(self):
        executor.submit(self.upload_class.upload_json, self.batch_payload)
        self.batch_payload = []
    
    def add_payload_to_batch(self,snap_time, flow_counter, gps_data,imu_data, image):
        self.batch_payload.append({
                        "timestamp": snap_time.isoformat(),
                        "flow_meter_counter": flow_counter,
                        "latitude":gps_data['latitude'],
                        "longitude": gps_data['longitude'],
                        "speed_kmh":gps_data['speed_kmh'],
                        "heading":gps_data['course'],
                        "IMU": imu_data.copy(),
                        "image_base_64":image})
        
        
        if len(self.batch_payload)==batch_size:
            self.flash_batch()
            gc.collect()

    def run(self):
        """The main loop of the session"""
        print("in session running.....")
        should_i_snap_image = 0
    
        while self.running:
        
            gps_data = get_gps_data()
            if gps_data['fix_status'] == 'No Fix':
                gps_data = {
                'latitude': 0.0,
                'longitude': 0.0,
                'altitude': 0.0,
                'timestamp': time.time(),
                'speed_kmh': 0,
                'course': 0,
                'fix_quality': None,
                'satellites': None,
                'gps_timestamp': None
                }
        
        
            print(f"lat:{gps_data['latitude']} lon:{gps_data['longitude']}")
            image = None
            if camera_connected and should_i_snap_image == self.camera_interval:
                image = self.camera.snap_as_base64()
                should_i_snap_image = 0
            elif camera_connected:
                should_i_snap_image +=1
 
            litter_per_hour = 0
            if flow_meter_connected:
                flow_counter = get_counter_and_reset()
                litter_per_hour = (flow_counter/flow_meter_pulses_per_litter)/interval_in_hours
                    
            imu_data = self.imu_manager.get_imu_buffer_and_reset()
                
            snap_time = datetime.now()
                
            self.add_payload_to_batch(snap_time, litter_per_hour, gps_data,imu_data, image)
                
            sleep(self.interval)
        
    def start(self) -> bool:
        """
        Start the session

        @return: True if the session was started, False if the session was already running
        """

        if self.running:
            return False
        
        self.running = True
        
        #start flow meter counter thread
        if flow_meter_connected:
          setup_flow_meter()

        # initiate IMU
        # Create global instance
        self.imu_manager = IMUManager(imu_rate_per_second)
 
        self.start_time = datetime.now()
        
        # Initialize camera if enabled
        if camera_connected:
            try:
                self.camera = Camera(self.camera_index)
            except Exception as e:
                print(f"Camera is disconnected or cannot be opened: {e}")
                print("Continue without image capturing")
                self.camera = None
        else:
            self.camera = None
            
        self.thread = Thread(target=self.run)
        self.thread.start()

        return True

    def end(self) -> bool:
        """
        End the session

        @return: True if the session was ended, False if the session was not running
        """

        if not self.running:
            return False

        self.running = False
        self.start_time = None
        
        if self.camera:
          self.camera.release()
        cleanup()

        print('Waiting for uploads to finish')

        self.thread.join()
        
        return True