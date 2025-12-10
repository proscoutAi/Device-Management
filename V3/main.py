import sys
import time
import uuid
from time import sleep

from button_led_manager import ButtonLEDManager, LEDColor
from gpiozero import LED, Button
from session import Session

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


Blue = LED(17)
'''
Yellow=LED(18)
Left = Button(27)
Right= Button(26)
'''
def main():
    led_manager = ButtonLEDManager()
    try:
        print(f"{time.ctime(time.time())}: Trying to start main application!!!!!")
        session = Session()
        if session.start():
            print(f"{time.ctime(time.time())}: Session started successfully")
        else:
            print(f"{time.ctime(time.time())}: Failed to start session")
            led_manager.turn_on(LEDColor.RED)
            return
            
        # Keep main thread alive and handle shutdown gracefully
        while True:
            Blue.toggle()
            sleep(1)
            
    except KeyboardInterrupt:
        print(f"{time.ctime(time.time())}: Shutting down...")
        if 'session' in locals():
            session.end()
    except Exception as e:
        print(f"{time.ctime(time.time())}: Fatal error in main: {e}")
        if 'session' in locals():
            session.end()
        


if __name__ == '__main__':
    main()
