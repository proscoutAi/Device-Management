import socket
import threading
import time
from enum import Enum


class LEDColor(Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"

class LedsManager:
    _instance = None
    _lock = threading.Lock()
    _sock_path = "/tmp/led.sock"

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(LedsManager, cls).__new__(cls)
        return cls._instance

    def _send_command(self, command: bytes):
        """Connect, send command, and close connection."""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(self._sock_path)
            sock.sendall(command)
            sock.close()
        except Exception as e:
            print(f"{time.ctime(time.time())}:Error sending LED command: {e}")

    def turn_on(self, color: LEDColor):
        print(f"{time.ctime(time.time())}:Turning on LED {color.value}")
        self._send_command(f"{color.value}:on\n".encode())

    def blink(self, color: LEDColor, speed: int):
        print(f"{time.ctime(time.time())}:Blinking LED {color.value} at {speed}ms")
        self._send_command(f"{color.value}:blink:{speed}\n".encode())

    def turn_off(self):
        print(f"{time.ctime(time.time())}:Turning off LED")
        self._send_command(b"off\n")
        
        
class LedsManagerService:
    _instance = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(LedsManagerService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if LedsManagerService._initialized:
            return
        with LedsManagerService._lock:
            if LedsManagerService._initialized:
                return
            self.running = False
            self.calibrate = False
            self.gps_online = True
            self.cellular_online = True
            self.charging = 0 # 0-10 if zero not charging, 10 fully, faster blinking closer to finish.
            self.leds_manager = LedsManager()
            LedsManagerService._initialized = True
        
    def start_running(self):
        if not self.running:
            self.running = True
            self._update_leds()
        self._print_state()
        
    def stop_running(self):
        if not self.running:
            self.running = False
            self._update_leds()
        self._print_state()
        
    def start_calibrate(self):
        if not self.calibrate:
            self.calibrate = True
            self._update_leds()
        self._print_state()
        
    def stop_calibrate(self):
        if self.calibrate:
            self.calibrate = False
            self._update_leds()
        self._print_state()
        
    def set_gps_online(self):
        if not self.gps_online:
            self.gps_online = True
            self._update_leds()
        self._print_state()
        
    def set_gps_offline(self):
        if self.gps_online:
            self.gps_online = False
            self._update_leds()
        self._print_state()
        
    def set_cellular_online(self):
        if not self.cellular_online:
            self.cellular_online = True
            self._update_leds()
        self._print_state()
        
    def set_cellular_offline(self):
        if self.cellular_online:
            self.cellular_online = False
            self.offline = True
            self._update_leds()
        self._print_state()
        
    def start_charging(self, charging_percentage: int):
        if self.charging != charging_percentage:
            self.charging = charging_percentage
            self._update_leds()
            self._print_state()
        
    def stop_charging(self):
        if self.charging != 0:
            self.charging = 0
            self._update_leds()
            self._print_state()
        
    def _update_leds(self):
        if self.calibrate:
            self.leds_manager.blink(LEDColor.GREEN, 500)
        elif not self.gps_online:
            self.leds_manager.blink(LEDColor.RED, 500)
        elif not self.cellular_online:
            self.leds_manager.blink(LEDColor.RED, 500)
        elif self.charging == 10:
            self.leds_manager.turn_on(LEDColor.Blue)
        elif self.charging > 0:
            self.leds_manager.blink(LEDColor.BLUE, (10 - self.charging) * 100)
        elif self.running:
            self.leds_manager.turn_on(LEDColor.GREEN)
        else:
            self.leds_manager.turn_on(LEDColor.RED)
            
    def _print_state(self):
        print(f"{time.ctime(time.time())}:LedsManagerService state: running={self.running}, calibrate={self.calibrate}, gps={self.gps_online}, cellular={self.cellular_online}, charging={self.charging}")