import threading
import time

from gpiozero import DigitalInputDevice, DigitalOutputDevice

from leds_manager import DockingState, LedsManagerService

DOCKING_TX = 6
DOCKING_RX = 13

class DockingManager:
    def __init__(self):
        self.leds_manager = LedsManagerService()
        self._docking_tx_pin = None
        self._docking_rx_pin = None
        
        # Initialize GPIO pin 6 as output
        try:
            self._docking_tx_pin = DigitalOutputDevice(DOCKING_TX)
            # Set pin 6 to HIGH
            self._docking_tx_pin.on()
        except Exception as e:
            print(f"{time.ctime(time.time())}:DockingManager: Error initializing output pin 6: {e}")
            raise RuntimeError(f"Failed to initialize output GPIO pin 6: {e}")
        
        # Initialize GPIO pin 13 as input with pull-down
        try:
            self._docking_rx_pin = DigitalInputDevice(DOCKING_RX, pull_up=False)
        except Exception as e:
            print(f"{time.ctime(time.time())}:DockingManager: Error initializing input pin 13: {e}")
            raise RuntimeError(f"Failed to initialize input GPIO pin 13: {e}")
        
        # Thread management
        self.monitor_thread = None
        self.monitor_active = False

    def run(self):
        """
        Start monitoring GPIO pin 13 using wait_for_active/wait_for_inactive.
        """
        if self.monitor_thread is not None and self.monitor_thread.is_alive():
            return
        
        # Check initial state of pin 13
        if self._docking_rx_pin.is_active:
            self.leds_manager.set_docking_state(DockingState.DOCKED)
            print(f"{time.ctime(time.time())}:DockingManager: Initial state - pin 13 is HIGH, setting DOCKED")
        else:
            self.leds_manager.set_docking_state(DockingState.UNDOCKED)
            print(f"{time.ctime(time.time())}:DockingManager: Initial state - pin 13 is LOW, setting UNDOCKED")
        
        # Start monitoring thread
        self.monitor_active = True
        self.monitor_thread = threading.Thread(target=self._monitor_rx_pin, daemon=True)
        self.monitor_thread.start()

    def _monitor_rx_pin(self):
        """
        Monitor pin 13 using wait_for_active/wait_for_inactive in a loop.
        """
        try:
            while self.monitor_active:
                # Wait for state change - alternate between waiting for active and inactive
                if self._docking_rx_pin.is_active:
                    # Currently HIGH, wait for LOW
                    self._docking_rx_pin.wait_for_inactive()
                    if not self.monitor_active:
                        break
                    print(f"{time.ctime(time.time())}:DockingManager: Pin 13 went LOW, setting UNDOCKED")
                    self.leds_manager.set_docking_state(DockingState.UNDOCKED)
                else:
                    # Currently LOW, wait for HIGH
                    self._docking_rx_pin.wait_for_active()
                    if not self.monitor_active:
                        break
                    print(f"{time.ctime(time.time())}:DockingManager: Pin 13 went HIGH, setting DOCKED")
                    self.leds_manager.set_docking_state(DockingState.DOCKED)
        except Exception as e:
            print(f"{time.ctime(time.time())}:DockingManager: Error in monitor thread: {e}")
        finally:
            print(f"{time.ctime(time.time())}:DockingManager: Monitor thread stopped")

    def stop(self):
        """
        Stop the monitoring thread.
        """
        self.monitor_active = False
        if self.monitor_thread is not None and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)
            self.monitor_thread = None

    def cleanup(self):
        """
        Clean up GPIO resources.
        """
        self.stop()
        
        if self._docking_rx_pin is not None:
            try:
                self._docking_rx_pin.close()
            except Exception:
                pass
        
        if self._docking_tx_pin is not None:
            try:
                self._docking_tx_pin.close()
            except Exception:
                pass

def main():
    docking_manager = DockingManager()
    docking_manager.run()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        docking_manager.stop()
        docking_manager.cleanup()

if __name__ == '__main__':
    main()