import sys
import time
import uuid
from time import sleep

from gpiozero import LED, Button
from leds_manager import LedsManagerService, SystemState
from session import Session

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


'''
Yellow=LED(18)
Left = Button(27)
Right= Button(26)
'''
def main():
    led_manager_service = LedsManagerService()
    try:
        print(f"{time.ctime(time.time())}: leds manager service initialized ")
        led_manager_service.set_system_state(SystemState.ON)
        print(f"{time.ctime(time.time())}: System state set to ON")
        print(f"{time.ctime(time.time())}: Trying to start main application!!!!!")
        session = Session()
        if session.start():
            print(f"{time.ctime(time.time())}: Session started successfully")
            
        else:
            print(f"{time.ctime(time.time())}: Failed to start session")
            led_manager_service.set_system_state(SystemState.MALFUNCTIONING)
            return
            
        # Keep main thread alive and handle shutdown gracefully
        while True:
            Blue.toggle()
            sleep(1)
            
    except KeyboardInterrupt:
        print(f"{time.ctime(time.time())}: Shutting down...")
        if 'session' in locals():
            session.end()
        led_manager_service.set_system_state(SystemState.MALFUNCTIONING)
    except Exception as e:
        print(f"{time.ctime(time.time())}: Fatal error in main: {e}")
        if 'session' in locals():
            session.end()
        led_manager_service.set_system_state(SystemState.MALFUNCTIONING)


if __name__ == '__main__':
    main()
