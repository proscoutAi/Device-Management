import subprocess
import re
import time
from datetime import datetime

def get_coordinates():
        """Get current GPS coordinates"""
        try:
            # Get location data
            result = subprocess.run([
                'mmcli', '--location-get'], capture_output=True, text=True, check=True)
            
            output = result.stdout
            
            # Parse latitude and longitude
            lat_match = re.search(r'latitude:\s*([+-]?\d+\.\d+)', output)
            lon_match = re.search(r'longitude:\s*([+-]?\d+\.\d+)', output)
            alt_match = re.search(r'altitude:\s*([+-]?\d+\.\d+)', output)
            
            if lat_match and lon_match:
                return {
                    'latitude': float(lat_match.group(1)),
                    'longitude': float(lon_match.group(1)),
                    'altitude': float(alt_match.group(1)) if alt_match else None,
                    'timestamp': time.time()
                }
            else:
                return None
                
        except subprocess.CalledProcessError as e:
            print(f"Error getting GPS coordinates: {e}")
            return None