import subprocess
import time
import threading



def is_wifi_connected():
    """Fast check - typically completes in <10ms"""
    try:
        result = subprocess.run(
            ['ip', 'addr', 'show', 'wlan0'],
            capture_output=True,
            text=True,
            timeout=1  # Short timeout just in case
        )
        return 'state UP' in result.stdout and 'inet ' in result.stdout
    except:
        return False

# Optional: Cache the result for a few seconds
# Thread-safe cache variables
_cache_lock = threading.Lock()
last_wifi_check = 0
wifi_status_cache = False
WIFI_CHECK_INTERVAL = 5  # Check WiFi status every 5 seconds

def is_wifi_connected_cached():
    """Check WiFi status but cache result for a few seconds (thread-safe)"""
    global last_wifi_check, wifi_status_cache
    
    current_time = time.time()
    
    # Use lock to ensure atomic check-and-update
    with _cache_lock:
        # Check if cache is still valid
        if current_time - last_wifi_check > WIFI_CHECK_INTERVAL:
            # Cache expired - update it
            wifi_status_cache = is_wifi_connected()
            last_wifi_check = current_time
        
        # Return cached value (protected by lock)
        return wifi_status_cache