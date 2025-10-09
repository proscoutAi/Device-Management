from datetime import datetime
from threading import Thread
from time import sleep
import time

import psutil

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
print(f"{time.ctime(time.time())}:working cloud url is:{cloud_function_url}")
batch_size = config.getint('Setup', 'batch_size')
imu_rate_per_second = config.getint('Setup', 'imu_rate_per_second')
interval_in_hours = sleep_interval/3600
flow_meter_pulses_per_litter = config.getint('Setup', 'flow_meter_pulses_per_litter')

executor = ThreadPoolExecutor(max_workers=3)

# Read the unique identifier (UUID or MAC address)
with open("/home/proscout/ProScout-master/device-manager/device_id.txt", "r") as f:
      client_device_id = f.read().strip()

time_format = '%Y-%m-%d_%H-%M-%S'

def log_system_status():
    """Standalone function to log system status"""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        
        # Get ppp0 stats
        net_stats = psutil.net_io_counters(pernic=True)
        if 'ppp0' in net_stats:
            ppp0 = net_stats['ppp0']
            bandwidth_info = f"ppp0: {ppp0.bytes_sent} sent, {ppp0.bytes_recv} recv"
        else:
            bandwidth_info = "ppp0: not found"
        
        timestamp = time.ctime(time.time())
        print(f"{timestamp}:📊 CPU: {cpu_percent:.1f}%, "
              f"RAM: {memory.percent:.1f}% ({memory.used/1024/1024:.0f}MB), "
              f"{bandwidth_info}")
              
    except Exception as e:
        print(f"{time.ctime(time.time())}:📊 System monitoring error: {e}")


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
        self.offline_upload_thread = None
        self.upload_threads = []
        self.upload_class = CloudFunctionClient(cloud_function_url,client_device_id,sleep_interval)
        self.batch_payload = []
        self.imu_manager = None
        
        # IMU health monitoring
        self.imu_last_data_time = time.time()
        self.imu_restart_attempts = 0
        self.max_imu_restarts = 5
        self.imu_timeout_seconds = 30  # If no IMU data for 30 seconds, restart
        
    
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
                        "image_base_64":image,
                        "gps_fix": gps_data['fix_status']!='No Fix'})
        
        
        if len(self.batch_payload)==batch_size:
            self.flash_batch()
            gc.collect()

    def check_imu_health(self):
        """Check if IMU is providing data and restart if needed"""
        current_time = time.time()
        
        # Check if IMU thread is still alive
        if not self.imu_manager or not self.imu_manager.thread.is_alive():
            print(f"{time.ctime(time.time())}:IMU thread has died!")
            log_system_status()
            return self.restart_imu()
        
        # Check if we're getting fresh data
        time_since_data = current_time - self.imu_last_data_time
        if time_since_data > self.imu_timeout_seconds:
            print(f"{time.ctime(time.time())}:No IMU data received for {time_since_data:.1f} seconds")
            log_system_status()
            return self.restart_imu()
        
        return True
    
    def restart_imu(self):
        """Attempt to restart the IMU manager"""
        if self.imu_restart_attempts >= self.max_imu_restarts:
            print(f"{time.ctime(time.time())}:Maximum IMU restart attempts ({self.max_imu_restarts}) reached. Giving up on IMU.")
            return False
        
        self.imu_restart_attempts += 1
        print(f"{time.ctime(time.time())}:Attempting IMU restart #{self.imu_restart_attempts}")
        
        try:
            # Stop existing IMU manager
            if self.imu_manager:
                print(f"{time.ctime(time.time())}:Stopping existing IMU manager...")
                self.imu_manager.running = False
                if self.imu_manager.thread.is_alive():
                    self.imu_manager.thread.join(timeout=10)
                self.imu_manager = None
                gc.collect()
            
            # Wait a moment for cleanup
            time.sleep(2)
            
            # Create new IMU manager
            print(f"{time.ctime(time.time())}:Creating new IMU manager...")
            self.imu_manager = IMUManager(imu_rate_per_second)
            
            # Reset timing
            self.imu_last_data_time = time.time()
            
            print(f"{time.ctime(time.time())}:IMU restart successful!")
            return True
            
        except Exception as e:
            print(f"{time.ctime(time.time())}:IMU restart failed: {e}")
            self.imu_manager = None
            return False

    def run(self):
        """The main loop of the session"""
        print(f"{time.ctime(time.time())}:in session running.....")
        should_i_snap_image = 0
        imu_check_counter = 0
        imu_check_interval = 10  # Check IMU health every 10 loops
        log_performance = 0 #log perfomance once a minute
    
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
                'gps_timestamp': None,
                'fix_status': 'No Fix'
                }
        
        
            #print(f"lat:{gps_data['latitude']} lon:{gps_data['longitude']}")
            image = None
            if camera_connected and should_i_snap_image == self.camera_interval:
                image = self.camera.snap_as_base64()
                should_i_snap_image = 0
            elif camera_connected:
                should_i_snap_image +=1
 
            litter_per_hour = 0
            if flow_meter_connected:
                flow_counter = get_counter_and_reset()
                litter_per_hour = flow_counter/flow_meter_pulses_per_litter
            
            # Get IMU data with health checking
            imu_data = []
            if self.imu_manager:
                try:
                    imu_data = self.imu_manager.get_imu_buffer_and_reset()
                    
                    # Update last data time if we got data
                    if imu_data:
                        self.imu_last_data_time = time.time()
                        # Reset restart attempts on successful data
                        if self.imu_restart_attempts > 0:
                            print(f"{time.ctime(time.time())}:IMU data flowing normally again")
                            self.imu_restart_attempts = 0
                    
                except Exception as e:
                    print(f"{time.ctime(time.time())}:Error getting IMU data: {e}")
                    imu_data = []
            
            # Periodic IMU health check
            imu_check_counter += 1
            if imu_check_counter >= imu_check_interval:
                imu_check_counter = 0
                if not self.check_imu_health():
                    print(f"{time.ctime(time.time())}:IMU health check failed - continuing without IMU data")
                
            snap_time = datetime.now()
                
            self.add_payload_to_batch(snap_time, litter_per_hour, gps_data, imu_data, image)
            log_performance += 1
            if log_performance ==60:
                log_system_status()
                log_performance = 0
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
        try:
            self.imu_manager = IMUManager(imu_rate_per_second)
            self.imu_last_data_time = time.time()
            print(f"{time.ctime(time.time())}:IMU initialized successfully")
        except Exception as e:
            print(f"{time.ctime(time.time())}:Failed to initialize IMU: {e}")
            print(f"{time.ctime(time.time())}:Continuing without IMU data")
            self.imu_manager = None
 
        self.start_time = datetime.now()
        
        # Initialize camera if enabled
        if camera_connected:
            try:
                self.camera = Camera(self.camera_index)
            except Exception as e:
                print(f"{time.ctime(time.time())}:Camera is disconnected or cannot be opened: {e}")
                print(f"{time.ctime(time.time())}:Continue without image capturing")
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
        
        # Properly stop IMU manager
        if self.imu_manager:
            print("Stopping IMU manager...")
            self.imu_manager.running = False
            if self.imu_manager.thread.is_alive():
                self.imu_manager.thread.join(timeout=10)
        
        return True