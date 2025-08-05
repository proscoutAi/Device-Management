import threading
import time
import lgpio
import atexit
import signal
import sys

FLOW_PIN = 5
pulse_count = 0
lock = threading.Lock()
chip = None
callback_id = None
cleanup_done = False
polling_thread = None
polling_active = False

def pulse_callback(chip_id, gpio, level, timestamp):
    global pulse_count
    
    # Debug: Always print callback triggers
    print(f"{time.ctime(time.time())}:🔥 CALLBACK: Pin {gpio}, Level {level}, Time {timestamp}")
    
    # Count falling edges (1 -> 0 transitions) and rising edges (0 -> 1)
    with lock:
        pulse_count += 1
        print(f"{time.ctime(time.time())}:✅ Pulse counted via callback! Total: {pulse_count}")

def polling_monitor():
    """Backup polling method if callbacks don't work"""
    global pulse_count, polling_active
    
    if chip is None:
        return
    
    print("🔄 Starting polling monitor...")
    last_state = lgpio.gpio_read(chip, FLOW_PIN)
    
    while polling_active:
        try:
            current_state = lgpio.gpio_read(chip, FLOW_PIN)
            
            # Detect ANY state change (both rising and falling edges)
            if last_state == 1 and current_state == 0:
                with lock:
                    pulse_count += 1
                    """print(f"📈 POLLING: State change {last_state}→{current_state}! Total: {pulse_count}")"""
            last_state = current_state
            
            time.sleep(0.001)  # Check every 1ms
            
        except Exception as e:
            print(f"{time.ctime(time.time())}:❌ Polling error: {e}")
            break
    
    print(f"{time.ctime(time.time())}:🛑 Polling monitor stopped")

def get_counter_and_reset():
    global pulse_count
    with lock:
        counter = pulse_count
        pulse_count = 0
    """print(f"📊 Returning counter: {counter}, reset to 0")"""
    return counter

def cleanup():
    global chip, callback_id, cleanup_done, polling_active, polling_thread
    
    if cleanup_done:
        return
        
    cleanup_done = True
    print(f"{time.ctime(time.time())}:🧹 Cleaning up GPIO...")
    
    # Stop polling thread
    polling_active = False
    if polling_thread and polling_thread.is_alive():
        polling_thread.join(timeout=1)
        print(f"{time.ctime(time.time())}:✅ Polling thread stopped")
    
    try:
        if callback_id is not None:
            callback_id.cancel()
            callback_id = None
            print(f"{time.ctime(time.time())}:✅ Callback cancelled")
    except Exception as e:
        print(f"{time.ctime(time.time())}:❌ Error canceling callback: {e}")
    
    try:
        if chip is not None:
            try:
                lgpio.gpio_free(chip, FLOW_PIN)
                print(f"{time.ctime(time.time())}:✅ GPIO pin {FLOW_PIN} freed")
            except:
                pass
                
            lgpio.gpiochip_close(chip)
            chip = None
            print(f"{time.ctime(time.time())}:✅ GPIO chip closed")
    except lgpio.error as e:
        if "unknown handle" not in str(e):
            print(f"{time.ctime(time.time())}:❌ Error closing GPIO chip: {e}")
    except Exception as e:
        print(f"{time.ctime(time.time())}:❌ Unexpected error closing GPIO chip: {e}")

def signal_handler(sig, frame):
    cleanup()
    sys.exit(0)

def setup_flow_meter():
    global chip, callback_id, polling_thread, polling_active
    
    print(f"{time.ctime(time.time())}:🚀 Setting up flow meter on GPIO pin {FLOW_PIN}...")
    
    # Force cleanup any existing resources first
    cleanup()
    time.sleep(0.1)  # Give threads time to stop
    
    try:
        for attempt in range(5):
            try:
                # Open GPIO chip
                chip = lgpio.gpiochip_open(0)
                print(f"{time.ctime(time.time())}:✅ GPIO chip opened: {chip}")
                
                # Claim pin as input with pull-up
                lgpio.gpio_claim_input(chip, FLOW_PIN, lgpio.SET_PULL_UP)
                print(f"{time.ctime(time.time())}:✅ GPIO pin {FLOW_PIN} claimed as input with pull-up")
                
                # Read initial state
                initial_state = lgpio.gpio_read(chip, FLOW_PIN)
                print(f"{time.ctime(time.time())}:📍 Initial pin state: {initial_state}")
                break
            except Exception as e:
                if "GPIO busy" in str(e) and attempt < 4:
                    print(f"{time.ctime(time.time())}:⚠️ GPIO busy, retrying in 1s... (attempt {attempt + 1}/5)")
                    cleanup()
                    time.sleep(1.0)
                else:
                    raise
        
        # Reset cleanup flag since we're starting fresh
        global cleanup_done
        cleanup_done = False
        
        # Start polling
        polling_active = True
        polling_thread = threading.Thread(target=polling_monitor, daemon=True)
        polling_thread.start()
        print("{time.ctime(time.time())}:✅ Polling monitor started")
        
        # Register cleanup handlers
        atexit.register(cleanup)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        print(f"🎉 Flow meter setup complete!")
        
    except lgpio.error as e:
        print(f"{time.ctime(time.time())}:❌ GPIO Error during setup: {e}")
        cleanup()
        raise
    except Exception as e:
        print(f"{time.ctime(time.time())}:❌ Unexpected error during setup: {e}")
        cleanup()
        raise

# Initialize the flow meter
'''
if __name__ == "__main__":
    setup_flow_meter()
    print("Press Ctrl+C to exit...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting...")
else:
    setup_flow_meter()
'''
