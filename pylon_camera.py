from datetime import datetime
from threading import Thread
import time
from pypylon import pylon
from upload import upload_image
import os
import cv2
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=5)

# Read the unique identifier (UUID or MAC address)
with open("/home/proscout/ProScout-master/camera/device_id.txt", "r") as f:
      client_device_id = f.read().strip()

time_format = '%Y-%m-%d_%H-%M-%S'
path_format = 'device {device_id}/session {start_time}/'
file_format = 'snap {snap_time}.png'


def get_path(device_id: int, start_time: datetime) -> str:
    return path_format.format(device_id=device_id, start_time=start_time.strftime(time_format))


def get_filename(snap_time: datetime) -> str:
    return file_format.format(snap_time=snap_time.strftime(time_format))


class Pylon_Session:
    # Camera capture settings
    def capture_images(self):
        """Captures images every 5 seconds and uploads to Google Cloud Storage."""
        # Initialize camera
        

        try:
                grab_result = self.camera.RetrieveResult(10000, pylon.TimeoutHandling_ThrowException)
                if grab_result.GrabSucceeded():
                    # Save the image locally
                    image = pylon.PylonImage()
                    image.AttachGrabResultBuffer(grab_result)
                    
                    # Cleanup
                    image.Release()
                    grab_result.Release()
                else:
                    print("Failed to grab image.")
                
                
        except KeyboardInterrupt:
                print("Stopping image capture.")
        finally:
                self.camera.StopGrabbing()
                self.camera.Close()

            
    def __init__(self,  interval: int = 5):
        """
        @param camera_index: The index of the camera device to use
        @param interval: The interval in seconds between each image capture
        """

        self.running = False
        self.start_time = None
        self.interval = interval
        self.camera = None
        self.thread = None
        self.upload_threads = []
        self.converter = pylon.ImageFormatConverter()
        
    def run(self):
        """The main loop of the session"""

        while self.running:
         grab_result = self.camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
         if grab_result.GrabSucceeded():
             
            # Convert to OpenCV image
            image = self.converter.Convert(grab_result)
            image_array = image.GetArray()
            
            
            # Convert NumPy array to OpenCV BGR format
        
            snap_time = datetime.now()

            path = get_path(client_device_id, self.start_time)
            filename = get_filename(snap_time)

            executor.submit(upload_image, image_array, path, filename)

            time.sleep(self.interval)
            # Release image
            image.Release()
            grab_result.Release()
         else:
            print("Failed to grab image.")
    
    def start(self) -> bool:
        """
        Start the session

        @return: True if the session was started, False if the session was already running
        """

        if self.running:
            return False

        self.running = True
        self.start_time = datetime.now()
        self.camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
        self.camera.Open()
        
        # Set the camera resolution to its full sensor size
        self.camera.Width = 1936
        self.camera.Height = 1216
        
        self.converter.OutputPixelFormat = pylon.PixelType_RGB8packed
        self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
        self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

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
        print("Stopping image capture.")
        self.camera.StopGrabbing()
        self.camera.Close()
        print('Waiting for uploads to finish')

        self.thread.join()
        for upload_thread in self.upload_threads:
            upload_thread.join()

        return True

