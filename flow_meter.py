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
    print(f"🔥 CALLBACK: Pin {gpio}, Level {level}, Time {timestamp}")
    
    # Count falling edges (1 -> 0 transitions) and rising edges (0 -> 1)
    with lock:
        pulse_count += 1
        print(f"✅ Pulse counted via callback! Total: {pulse_count}")

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
            print(f"❌ Polling error: {e}")
            break
    
    print("🛑 Polling monitor stopped")

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
    print("🧹 Cleaning up GPIO...")
    
    # Stop polling thread
    polling_active = False
    if polling_thread and polling_thread.is_alive():
        polling_thread.join(timeout=1)
        print("✅ Polling thread stopped")
    
    try:
        if callback_id is not None:
            callback_id.cancel()
            callback_id = None
            print("✅ Callback cancelled")
    except Exception as e:
        print(f"❌ Error canceling callback: {e}")
    
    try:
        if chip is not None:
            lgpio.gpiochip_close(chip)
            chip = None
            print("✅ GPIO chip closed")
    except lgpio.error as e:
        if "unknown handle" not in str(e):
            print(f"❌ Error closing GPIO chip: {e}")
    except Exception as e:
        print(f"❌ Unexpected error closing GPIO chip: {e}")

def signal_handler(sig, frame):
    cleanup()
    sys.exit(0)

def setup_flow_meter():
    global chip, callback_id, polling_thread, polling_active
    
    print(f"🚀 Setting up flow meter on GPIO pin {FLOW_PIN}...")
    
    try:
        # Open GPIO chip
        chip = lgpio.gpiochip_open(0)
        print(f"✅ GPIO chip opened: {chip}")
        
        # Claim pin as input with pull-up
        lgpio.gpio_claim_input(chip, FLOW_PIN, lgpio.SET_PULL_UP)
        print(f"✅ GPIO pin {FLOW_PIN} claimed as input with pull-up")
        
        # Read initial state
        initial_state = lgpio.gpio_read(chip, FLOW_PIN)
        print(f"📍 Initial pin state: {initial_state}")
        
        # Try to set up callback first
        '''
        try:
            callback_id = lgpio.callback(chip, FLOW_PIN, lgpio.BOTH_EDGES, pulse_callback)
            print(f"✅ Callback registered: {callback_id}")
        except Exception as e:
            print(f"⚠️ Callback registration failed: {e}")
            callback_id = None
        '''
        # Start polling as backup
        polling_active = True
        polling_thread = threading.Thread(target=polling_monitor, daemon=True)
        polling_thread.start()
        print("✅ Polling monitor started")
        
        # Register cleanup handlers
        atexit.register(cleanup)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        print(f"🎉 Flow meter setup complete!")
        
        # Test the setup
        '''
        print("🧪 Testing for 5 seconds - ACTIVATE YOUR FLOW METER NOW!")
        time.sleep(5)
        
        with lock:
            if pulse_count > 0:
                print(f"✅ Flow meter is working! Detected {pulse_count} pulses during test")
            else:
                print("⚠️ No pulses detected during test - try activating the flow meter")
        '''
    except lgpio.error as e:
        print(f"❌ GPIO Error during setup: {e}")
        cleanup()
        raise
    except Exception as e:
        print(f"❌ Unexpected error during setup: {e}")
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
