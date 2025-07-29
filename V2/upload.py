from datetime import datetime
import os
from threading import Thread
import time

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
        self.offline_upload_sleep_interval = 600 #10 minutes between trying to upload offline data
        
        #starting a thread for unsent messages - offline
        self.thread = Thread(target=self.upload_offline_data)
        self.thread.start()

    def upload_json(self,batch_payload):
     try:

        json_txt = {"device_uuid": self.device_uuid,
                    "sessionTimestamp": self.session_start_time.isoformat(),
                    "sleep_time":self.sleep_interval,
                    "payload" : batch_payload
                    }

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
            print(f"save data to disk for offline upload when network restores")
            self.save_to_disk(json_txt)
            return {'error': f'Network error: {str(e)}'}
     except Exception as e:
            print(f"âŒ Unexpected error: {e}")
            return {'error': f'Unexpected error: {str(e)}'}
        
    def save_to_disk(self, data):
        """Save data to local disk when upload fails"""
        try:
            # Create offline data directory if it doesn't exist
            offline_dir = "/home/proscout/offline_data"
            os.makedirs(offline_dir, exist_ok=True)
            
            # Create filename with timestamp
            filename = f"offline_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(offline_dir, filename)
            
            # Save to file
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
                
            print(f"💾 Data saved to disk: {filepath}")
            
        except Exception as e:
            print(f"❌ Failed to save to disk: {e}")

    def upload_offline_data(self):
        """Upload any offline data when connection is restored"""
        offline_dir = "/home/proscout/offline_data"
        print("starting offline thread upload")
        
        while True:
            if not os.path.exists(offline_dir):
                print("no offline data found")
                time.sleep(self.offline_upload_sleep_interval)
            else:  
                for filename in os.listdir(offline_dir):
                    if filename.endswith('.json'):
                        filepath = os.path.join(offline_dir, filename)
                        try:
                            with open(filepath, 'r') as f:
                                data = json.load(f)
                            
                            print(f"Found unset data! uploading offline data:{data}")
                            # Try to upload
                            response = requests.post(
                                f"{self.cloud_function_url}/ingest",
                                json=data,
                                headers={'Content-Type': 'application/json'},
                                timeout=30
                            )
                            
                            if response.status_code == 201:
                                print(f"✅ Offline data uploaded: {filename}")
                                os.remove(filepath)  # Delete after successful upload
                            else:
                                print(f"❌ Failed to upload offline data: {filename}")
                                break  # Stop trying if upload fails
                                
                        except Exception as e:
                            print(f"❌ Error processing offline file {filename}: {e}")
                            
                time.sleep(self.offline_upload_sleep_interval)