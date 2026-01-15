import configparser
import gzip
import json
import os
import sys
import time
from datetime import datetime
from threading import Thread

import cv2
import requests
from leds_manager import CellularState, LedsManagerService
from numpy import ndarray
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
        self.led_manager_service = LedsManagerService()
        self.cloud_function_url = cloud_function_url.rstrip('/')
        self.device_uuid = device_uuid
        self.session_start_time = None
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
                    f"{self.cloud_function_url}/insert-device-data-raw",
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
                    self.led_manager_service.set_cellular_state(CellularState.ONLINE)
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
        self.led_manager_service.set_cellular_state(CellularState.NO_SIGNAL)
        try:
            # Create offline data directory if it doesn't exist
            offline_dir = "/home/proscout/offline_data"
            os.makedirs(offline_dir, exist_ok=True)
            
            # Create filename with timestamp
            filename = f"offline_data_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(offline_dir, filename)
            
            # Get sample timestamp info from payload for logging
            timestamp_info = ""
            if data and 'payload' in data and len(data['payload']) > 0:
                first_timestamp = data['payload'][0].get('timestamp', 'N/A')
                last_timestamp = data['payload'][-1].get('timestamp', 'N/A')
                gps_fix_count = sum(1 for p in data['payload'] if p.get('gps_fix', False))
                total_count = len(data['payload'])
                timestamp_info = f" | Timestamps: {first_timestamp} to {last_timestamp} | GPS fix: {gps_fix_count}/{total_count}"
            
            # Save to file
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
                
            print(f"{time.ctime(time.time())}:💾 Data saved to disk: {filepath}{timestamp_info}")
            
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
                        # Check if file is 0 bytes or empty before processing
                        if os.path.getsize(filepath) == 0:
                            print(f"{time.ctime(time.time())}:🗑️ Deleting 0-byte file: {filename}")
                            os.remove(filepath)
                            continue
                        
                        # Try to load JSON and catch formatting errors
                        try:
                            with open(filepath, 'r') as f:
                                data = json.load(f)
                        except json.JSONDecodeError as json_err:
                            # JSON formatting error - move to problematic directory
                            print(f"{time.ctime(time.time())}:❌ JSON formatting error in {filename}: {json_err}")
                            problematic_dir = os.path.join(offline_dir, "problematic")
                            os.makedirs(problematic_dir, exist_ok=True)
                            try:
                                problematic_path = os.path.join(problematic_dir, filename)
                                os.rename(filepath, problematic_path)
                                print(f"{time.ctime(time.time())}:📦 Moved corrupted file to problematic directory: {filename}")
                            except Exception as move_err:
                                print(f"{time.ctime(time.time())}:❌ Failed to move file {filename}: {move_err}")
                                # If move fails, delete it
                                try:
                                    os.remove(filepath)
                                    print(f"{time.ctime(time.time())}:🗑️ Deleted corrupted file: {filename}")
                                except:
                                    pass
                            continue  # Skip to next file
                        
                        print(f"{time.ctime(time.time())}:📤 Uploading offline data: {filename}")
                        
                        if len(data) == 0:
                            #corrupted file. delete and continue
                            print(f"{time.ctime(time.time())}:🗑️ Deleting empty data file: {filename}")
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
                                    f"{self.cloud_function_url}/insert-device-data-raw",
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
                                # This shouldn't happen here since we check earlier, but handle it anyway
                                print(f"{time.ctime(time.time())}:❌ JSON decode error during upload for {filename}: {e}")
                                problematic_dir = os.path.join(offline_dir, "problematic")
                                os.makedirs(problematic_dir, exist_ok=True)
                                try:
                                    problematic_path = os.path.join(problematic_dir, filename)
                                    os.rename(filepath, problematic_path)
                                    print(f"{time.ctime(time.time())}:📦 Moved corrupted file to problematic directory: {filename}")
                                except Exception as move_err:
                                    try:
                                        os.remove(filepath)
                                        print(f"{time.ctime(time.time())}:🗑️ Deleted corrupted file: {filename}")
                                    except:
                                        pass
                                break  # Exit retry loop and continue to next file
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
                            print(f"{time.ctime(time.time())}:💔 All upload attempts failed for {filename}, skipping and continuing to next file")
                            continue  # Skip this file and continue to next file
                            
                        time.sleep(1)  # Brief pause between uploads
                        
                    except Exception as e:
                        # Catch any other unexpected errors (file I/O, etc.)
                        error_msg = str(e)
                        # Check if it's a JSON-related error that wasn't caught earlier
                        if "JSON" in error_msg or "Expecting" in error_msg or "delimiter" in error_msg or "JSONDecodeError" in error_msg:
                            print(f"{time.ctime(time.time())}:❌ JSON formatting error in {filename}: {e}")
                            problematic_dir = os.path.join(offline_dir, "problematic")
                            os.makedirs(problematic_dir, exist_ok=True)
                            try:
                                problematic_path = os.path.join(problematic_dir, filename)
                                os.rename(filepath, problematic_path)
                                print(f"{time.ctime(time.time())}:📦 Moved corrupted file to problematic directory: {filename}")
                            except Exception as move_err:
                                print(f"{time.ctime(time.time())}:❌ Failed to move file {filename}: {move_err}")
                                try:
                                    os.remove(filepath)
                                    print(f"{time.ctime(time.time())}:🗑️ Deleted corrupted file: {filename}")
                                except:
                                    pass
                        else:
                            print(f"{time.ctime(time.time())}:❌ Error processing offline file {filename}: {e}")
                        time.sleep(2)  # Brief wait before trying next file
                        
                time.sleep(self.offline_upload_sleep_interval)
                
            except Exception as e:
                print(f"{time.ctime(time.time())}:❌ Error in offline upload thread: {e}")