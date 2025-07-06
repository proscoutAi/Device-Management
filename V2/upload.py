from datetime import datetime
import os

import cv2
from numpy import ndarray
import json
import sys
import configparser

import requests
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

class CloudFunctionClient:
    def __init__(self, cloud_function_url, device_uuid, sleep_interval):
        """
        Initialize the client
        
        Args:
            cloud_function_url: Your Cloud Function HTTP trigger URL
            device_uuid: Your device's UUID
            enable_camera: Whether to initialize camera for image capture
        """
        self.cloud_function_url = cloud_function_url.rstrip('/')
        self.device_uuid = device_uuid
        self.session_start_time = datetime.now()
        self.sleep_interval = sleep_interval

    def upload_json(self,timestamp,flow_meter_counter,gps_data,image):
     try:

        json_txt = {"device_uuid": self.device_uuid,
                               "sessionTimestamp": self.session_start_time.isoformat(),
                               "timestamp": timestamp.isoformat(),
                               "sleep_time":self.sleep_interval,
                               "flow_meter_counter": flow_meter_counter,
                               "latitude":gps_data['latitude'],
                               "longitude": gps_data['longitude'],
                               "speed_kmh":gps_data['speed_kmh'],
                               "heading":gps_data['heading'],
                               "image_base_64":image}

        #send json to google run function
        # Send HTTP POST request
        response = requests.post(
                f"{self.cloud_function_url}/ingest",
                json=json_txt,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
        if response.status_code == 201:
                print("âœ… Data sent successfully!")
                return response.json()
        else:
                print(f"âŒ Error: {response.status_code}")
                print(f"Response: {response.text}")
                return {'error': f'HTTP {response.status_code}: {response.text}'}
                
     except requests.exceptions.RequestException as e:
            print(f"âŒ Network error: {e}")
            return {'error': f'Network error: {str(e)}'}
     except Exception as e:
            print(f"âŒ Unexpected error: {e}")
            return {'error': f'Unexpected error: {str(e)}'}
            
