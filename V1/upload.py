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

imu_data = {
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

    def upload_json(self,timestamp,flow_meter_counter,gps_data,image,gps_data_dual):
     try:
        
        if gps_data['heading'] is None:
         gps_data['heading'] = 0.0
        batch_payload = [{
                        "timestamp": timestamp.isoformat(),
                        "flow_meter_counter": flow_meter_counter,
                        "latitude":gps_data['latitude'],
                        "longitude": gps_data['longitude'],
                        "speed_kmh":gps_data['speed_kmh'],
                        "heading":gps_data['heading'],
                        "IMU": gps_data_dual,
                        "image_base_64":None}]
        
        json_txt = {"device_uuid": self.device_uuid,
                    "sessionTimestamp": self.session_start_time.isoformat(),
                    "sleep_time":self.sleep_interval,
                    "payload" : batch_payload
                    }

        print(batch_payload)
        print(json_txt)        

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