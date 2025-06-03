from datetime import datetime
from threading import Thread
from time import sleep

from camera import Camera
from upload import upload_image,upload_json
from concurrent.futures import ThreadPoolExecutor
from flow_meter import get_counter_and_reset,cleanup,setup_flow_meter
import configparser
import os
from gps_manager import get_coordinates
import sys
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# read input folder from config file
if not os.path.exists('config.ini'):
    raise ValueError("Configuration file 'config.ini' not found. Please create it.")
config = configparser.ConfigParser()
config.read('config.ini')
sleep_interval = int(config.get('Setup','sleep_interval').strip('"').strip("'"))


executor = ThreadPoolExecutor(max_workers=5)

# Read the unique identifier (UUID or MAC address)
with open("/home/proscout/ProScout-master/camera/device_id.txt", "r") as f:
      client_device_id = f.read().strip()

time_format = '%Y-%m-%d_%H-%M-%S'
path_format = 'device {device_id}/session {start_time}/'
file_format = 'snap {snap_time}.png'
json_file = 'snap {snap_time}.json'



def get_path(device_id: int, start_time: datetime) -> str:
    return path_format.format(device_id=device_id, start_time=start_time.strftime(time_format))


def get_filename(snap_time: datetime) -> str:
    return file_format.format(snap_time=snap_time.strftime(time_format)),json_file.format(snap_time=snap_time.strftime(time_format))


class Session:
    """A class to represent a session of image capture"""

    default_interval = 3

    def __init__(self, camera_index: int = 0):
        """
        @param camera_index: The index of the camera device to use
        @param interval: The interval in seconds between each image capture
        """

        self.running = False
        self.start_time = None
        self.interval = sleep_interval
        self.camera_index = camera_index
        self.camera = None
        self.thread = None
        self.upload_threads = []
        

    def run(self):
        """The main loop of the session"""

        while self.running:
            image_arr = self.camera.snap()
            lat = 0
            lon = 0
            
            gps_data = get_coordinates()
            if gps_data is not None:
              if 'latitude' in gps_data and gps_data['latitude']:
                  lat = gps_data['latitude']
              if 'longitude' in gps_data and gps_data['longitude']:
                  lon = gps_data['longitude']
              
              print (f"lat:{lat} lon:{lon}")
              
              flow_counter = get_counter_and_reset()
              snap_time = datetime.now()

              path = get_path(client_device_id, self.start_time)
              filename,json_file = get_filename(snap_time)

              executor.submit(upload_image, image_arr, path, filename)
              executor.submit(upload_json,flow_counter,path,json_file,self.interval,lat,lon)

            sleep(self.interval)
        self.camera.release()
        cleanup()

    def start(self) -> bool:
        """
        Start the session

        @return: True if the session was started, False if the session was already running
        """

        if self.running:
            return False
        
        setup_flow_meter()

        self.running = True
        self.start_time = datetime.now()
        self.camera = Camera(self.camera_index)
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

        print('Waiting for uploads to finish')

        self.thread.join()
        for upload_thread in self.upload_threads:
            upload_thread.join()

        return True
