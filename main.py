from session import Session
import uuid
from gpiozero import LED,Button
from time import sleep
import time

Blue = LED(17)
Yellow=LED(18)
Left = Button(27)
Right= Button(26)

def main():
    """A main function to interact with sessions"""

    session = Session()
    
    Yellow.toggle()
   
    
    while True:
        
        if Left.is_pressed:
            if not Blue.value:
                
                print('Starting session')
#               Blue.on()
                Blue.toggle()
                sleep(0.2)

                session.start()
    
        elif Right.is_pressed:
            if Blue.value:
                print('Quitting')
#               Blue.off()
                Blue.toggle()
                sleep(0.2)

                session.end()
    

if __name__ == '__main__':
    main()
