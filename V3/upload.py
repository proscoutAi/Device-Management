from datetime import datetime
import gzip
import os
from threading import Thread
import time

import cv2
from numpy import ndarray
import json
import sys
import configparser

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
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
        
        self._setup_session()
        
        #starting a thread for unsent messages - offline
        self.thread = Thread(target=self.upload_offline_data)
        self.thread.daemon = True  # Make thread daemon so it exits when main program exits
        self.thread.start()

    def _setup_session(self):
        """Setup requests session with proper configuration"""
        self.session = requests.Session()
        
        # Configure adapter - minimal pooling since we close connections anyway
        adapter = HTTPAdapter(
            pool_connections=1,  # One pool (we only talk to one Cloud Run service)
            pool_maxsize=1,      # Only 1 connection since we're not reusing them
            max_retries=0        # Handle retries manually for better control
        )
        self.session.mount('https://', adapter)
        
        # Set session-level headers
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Connection': 'close',  # Force connection close after each request
            'User-Agent': f'ProScout-Device/{self.device_uuid}'
        })

    def _recreate_session(self):
        """Recreate session if connection issues persist"""
        print(f"{time.ctime(time.time())}:🔄 Recreating session due to connection issues")
        try:
            self.session.close()
        except:
            pass
        self._setup_session()

    def upload_json(self, batch_payload):
        max_retries = 2
        
        for attempt in range(max_retries + 1):
            try:
                json_txt = {
                    "device_uuid": self.device_uuid,
                    "sessionTimestamp": self.session_start_time.isoformat(),
                    "sleep_time": self.sleep_interval,
                    "payload": batch_payload
                }
                
                # Compress the JSON
                json_str = json.dumps(json_txt)
                compressed_data = gzip.compress(json_str.encode('utf-8'))

                # Send HTTP POST request
                response = self.session.post(
                    f"{self.cloud_function_url}/ingest",
                    data=compressed_data,
                    headers={
                        'Content-Type': 'application/json',
                        'Content-Encoding': 'gzip',
                        'Connection': 'close'
                    },
                    timeout=30
                )
                            
                if response.status_code == 201:
                    print(f"{time.ctime(time.time())}:✅ Data sent successfully!")
                    return response.json()
                else:
                    print(f"{time.ctime(time.time())}:❌ Error: {response.status_code}")
                    print(f"{time.ctime(time.time())}:Response: {response.text}")
                    return {'error': f'HTTP {response.status_code}: {response.text}'}
                    
            except (requests.exceptions.ConnectionError, 
                    requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.HTTPError) as e:
                print(f"🔌 Connection error (attempt {attempt + 1}/{max_retries + 1}): {e}")
                
                if attempt < max_retries:
                    # Recreate session on connection errors
                    self._recreate_session()
                    time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                    continue
                else:
                    # Final attempt failed, save to disk
                    print(f"{time.ctime(time.time())}:💾 All connection attempts failed, saving to disk")
                    if json_txt and len(batch_payload) > 0:
                        self.save_to_disk(json_txt)
                    return {'error': f'Connection error after {max_retries + 1} attempts: {str(e)}'}
                    
            except requests.exceptions.Timeout as e:
                print(f"⏱️ Timeout error (attempt {attempt + 1}/{max_retries + 1}): {e}")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    if json_txt and len(batch_payload) > 0:
                        self.save_to_disk(json_txt)
                    return {'error': f'Timeout error after {max_retries + 1} attempts: {str(e)}'}
                    
            except requests.exceptions.RequestException as e:
                print(f"🌐 Network error: {e}")
                if json_txt and len(batch_payload) > 0:
                    print(f"{time.ctime(time.time())}:💾 Saving data to disk for offline upload")
                    self.save_to_disk(json_txt)
                return {'error': f'Network error: {str(e)}'}
                
            except Exception as e:
                print(f"{time.ctime(time.time())}:❌ Unexpected error: {e}")
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
                
            print(f"{time.ctime(time.time())}:💾 Data saved to disk: {filepath}")
            
        except Exception as e:
            print(f"{time.ctime(time.time())}:❌ Failed to save to disk: {e}")

    def upload_offline_data(self):
        """Upload any offline data when connection is restored"""
        offline_dir = "/home/proscout/offline_data"
        print(f"{time.ctime(time.time())}:🚀 Starting offline data upload thread")
        
        while True:
            try:
                if not os.path.exists(offline_dir):
                    time.sleep(self.offline_upload_sleep_interval)
                    continue
                    
                files = [f for f in os.listdir(offline_dir) if f.endswith('.json')]
                if not files:
                    time.sleep(self.offline_upload_sleep_interval)
                    continue
                
                print(f"{time.ctime(time.time())}:📁 Found {len(files)} offline files to upload")
                
                for filename in sorted(files):  # Process files in order
                    filepath = os.path.join(offline_dir, filename)
                    try:
                        with open(filepath, 'r') as f:
                            data = json.load(f)
                        
                        print(f"{time.ctime(time.time())}:📤 Uploading offline data: {filename}")
                        
                        if len(data) == 0:
                            #currupted file. delete and continue
                            os.remove(filepath)
                            continue
                        
                        json_str = json.dumps(data)
                        compressed_data = gzip.compress(json_str.encode('utf-8'))
                        
                        # Try uploading with retry logic
                        upload_success = False
                        max_retries = 2
                        
                        for attempt in range(max_retries + 1):
                            try:
                                # Create a fresh session for each attempt
                                offline_session = requests.Session()
                                offline_session.headers.update({
                                    'Content-Type': 'application/json',
                                    'Content-Encoding': 'gzip',
                                    'Connection': 'close',
                                    'User-Agent': f'ProScout-Device/{self.device_uuid}-offline'
                                })
                                
                                response = offline_session.post(
                                    f"{self.cloud_function_url}/ingest",
                                    data=compressed_data,
                                    timeout=30
                                )
                                                
                                if response.status_code == 201:
                                    print(f"{time.ctime(time.time())}:✅ Offline data uploaded: {filename}")
                                    os.remove(filepath)  # Delete after successful upload
                                    upload_success = True
                                    break  # Success, exit retry loop
                                else:
                                    print(f"{time.ctime(time.time())}:❌ HTTP {response.status_code} for {filename} (attempt {attempt + 1}/{max_retries + 1})")
                                    if attempt < max_retries:
                                        time.sleep(2 ** attempt)  # Exponential backoff
                                    
                            except json.JSONDecodeError as e:
                                print(f"{time.ctime(time.time())}:❌ Corrupted JSON file {filename}: {e}")
                                print(f"{time.ctime(time.time())}:🗑️ Deleting corrupted file: {filename}")
                                os.remove(filepath)  # Delete corrupted file
                                continue  # Skip to next file
                            except (requests.exceptions.ConnectionError, 
                                    requests.exceptions.ChunkedEncodingError,
                                    requests.exceptions.HTTPError) as e:
                                print(f"🔌 Offline upload connection error (attempt {attempt + 1}/{max_retries + 1}): {e}")
                                if attempt < max_retries:
                                    time.sleep(2 ** attempt)  # Exponential backoff
                                    
                            except requests.exceptions.Timeout as e:
                                print(f"⏱️ Offline upload timeout (attempt {attempt + 1}/{max_retries + 1}): {e}")
                                if attempt < max_retries:
                                    time.sleep(2 ** attempt)
                                    
                            except Exception as e:
                                print(f"{time.ctime(time.time())}:❌ Unexpected error uploading {filename}: {e}")
                                break  # Don't retry on unexpected errors
                                
                            finally:
                                try:
                                    offline_session.close()
                                except:
                                    pass
                        
                        if not upload_success:
                            print(f"{time.ctime(time.time())}:💔 All upload attempts failed for {filename}, will retry later")
                            break  # Stop processing more files, will try again in next cycle
                            
                        time.sleep(1)  # Brief pause between uploads
                        
                    except Exception as e:
                        print(f"{time.ctime(time.time())}:❌ Error processing offline file {filename}: {e}")
                        time.sleep(5)  # Wait before trying next file
                        
                time.sleep(self.offline_upload_sleep_interval)
                
            except Exception as e:
                print(f"{time.ctime(time.time())}:❌ Error in offline upload thread: {e}")