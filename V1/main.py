from session import Session
import uuid
from gpiozero import LED,Button
from time import sleep
import time
import sys
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

Blue = LED(17)
Yellow=LED(18)
Left = Button(27)
Right= Button(26)

def main():
    """A main function to interact with sessions"""

    session = Session()
    session.start()
    
    while True:

        Blue.toggle()
        sleep(0.2)

        


if __name__ == '__main__':
    main()
