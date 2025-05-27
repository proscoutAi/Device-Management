import os

import cv2
from google.cloud import storage
from numpy import ndarray
import json

# https://cloud.google.com/docs/authentication/provide-credentials-adc#local-dev

# Connect to Google Cloud Storage
upload_bucket = 'unet-inference'

storage_client = storage.Client()
bucket = storage_client.bucket(upload_bucket)

# Create a temporary storage directory
temp_storage = 'temp/'

if not os.path.exists(temp_storage):
    os.makedirs(temp_storage)

for file in os.listdir(temp_storage):
    os.remove(temp_storage + file)
def upload_image(image: ndarray, path: str, filename: str):
    try:
        # Compress and save to memory
        _, compressed_img = cv2.imencode('.jpg', image, 
            [cv2.IMWRITE_JPEG_QUALITY, 75])

        # Upload directly from memory
        blob = bucket.blob(path + filename)
        blob.upload_from_string(
            compressed_img.tobytes(), 
            content_type='image/jpeg',
            timeout=60  # Add timeout
        )
    except Exception as e:
        print(f'Upload failed: {e}')

def upload_json(counter, path: str, filename: str,sleep_interval):
    try:
        blob = bucket.blob(path + filename)
        json_txt = json.dumps({"counter": counter, "interval": sleep_interval})

        #print(json_txt)
        blob.upload_from_string(
                json_txt, 
                content_type='text/plain',
                timeout=60  # Add timeout
            )
    except Exception as e:
        print(f'Upload failed: {e}')
