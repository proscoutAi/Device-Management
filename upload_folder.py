"""
This script uploads a local folder of images to the unet-inference bucket.
It extracts the timestamps from the image metadata.

We assume the first fetched image is the oldest (which identifies the start of the session).
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import cv2
import exifread
from tqdm import tqdm

from session import get_path, get_filename
from upload import upload_image

datetime_tag = 'EXIF DateTimeOriginal'
exif_datetime_format = '%Y:%m:%d %H:%M:%S'


def upload_folder(folder_path: str, device_id: int):
    """
    Uploads all images from a folder to the unet-inference bucket.

    @param folder_path: The path to the folder containing the images
    @param device_id: The ID of the device that captured the images
    """

    session_timestamp = None
    threads = 8

    futures = []

    with ThreadPoolExecutor(max_workers=threads) as executor:
        for filename in tqdm(os.listdir(folder_path), desc='Uploading images'):
            if filename.lower().endswith('.jpg'):
                with open(folder_path + filename, 'rb') as image_file:
                    tags = exifread.process_file(image_file)
                    timestamp = tags[datetime_tag]
                    timestamp = datetime.strptime(str(timestamp), exif_datetime_format)

                    session_timestamp = session_timestamp or timestamp

                    image_arr = cv2.imread(folder_path + filename)

                    path = get_path(device_id, session_timestamp)
                    file = get_filename(timestamp)

                    future = executor.submit(upload_image, image_arr, path, file)
                    futures.append(future)

    print('Waiting for uploads...')


# Tested on local data
if __name__ == '__main__':
    upload_folder('../res/G0051516/', 1)