from session import Session
from time import sleep
import readchar
import time

def main():
    """A main function to interact with sessions"""

    session = Session()
    
    print("press 'a' to start, 'b' to stop, 'q' to quit")
    while True:
        
        #choice = input('Choice: ')
        # Wait for key press
        
        key = readchar.readkey()
    
        # Print the key that was pressed
        print(f"You pressed: {key}")
    
        # Do something based on the key
        if key == 'a':
          print("You pressed 'a' - doing task A")
          sleep(0.2)
          session.start()
          # Code for task A
        elif key == 'b':
          print("You pressed 'b' - doing task B")
          sleep(0.2)
          session.end()
         # Code for task B
        elif key == 'q':
          print("Quitting...")
          break
    
        # Small delay
        time.sleep(0.1)
        
        

if __name__ == '__main__':
    main()
