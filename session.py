from datetime import datetime
from threading import Thread
from time import sleep

from camera import Camera
from upload import upload_image
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=5)

# Read the unique identifier (UUID or MAC address)
with open("/Users/ronenrayten/Spray Detection MVP/SprayDetectionUnet/ProScout-master/camera/device_id.txt", "r") as f:
      client_device_id = f.read().strip()

time_format = '%Y-%m-%d_%H-%M-%S'
path_format = 'device {device_id}/session {start_time}/'
file_format = 'snap {snap_time}.png'


def get_path(device_id: int, start_time: datetime) -> str:
    return path_format.format(device_id=device_id, start_time=start_time.strftime(time_format))


def get_filename(snap_time: datetime) -> str:
    return file_format.format(snap_time=snap_time.strftime(time_format))


class Session:
    """A class to represent a session of image capture"""

    default_interval = 3

    def __init__(self, camera_index: int = 0, interval: int = default_interval):
        """
        @param camera_index: The index of the camera device to use
        @param interval: The interval in seconds between each image capture
        """

        self.running = False
        self.start_time = None
        self.interval = interval
        self.camera_index = camera_index
        self.camera = None
        self.thread = None
        self.upload_threads = []

    def run(self):
        """The main loop of the session"""

        while self.running:
            image_arr = self.camera.snap()
            snap_time = datetime.now()

            path = get_path(client_device_id, self.start_time)
            filename = get_filename(snap_time)

            executor.submit(upload_image, image_arr, path, filename)

            sleep(self.interval)
        self.camera.release()

    def start(self) -> bool:
        """
        Start the session

        @return: True if the session was started, False if the session was already running
        """

        if self.running:
            return False

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