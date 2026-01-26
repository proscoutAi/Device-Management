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
        
class SystemState(Enum):
    ON = "on"
    BOOTING = "booting"
    MALFUNCTIONING = "malfunctioning"

class DockingState(Enum):
    DOCKED = "docked"
    UNDOCKED = "undocked"

class GPSState(Enum):
    ONLINE = "online"
    NO_FIX = "no_fix"
    
class CellularState(Enum):
    ONLINE = "online"
    NO_SIGNAL = "no_signal"
    
class IMUState(Enum):
    ONLINE = "online"
    CALIBRATING = "calibrating"
    ERROR = "error"

class DownloadingState(Enum):
    DOWNLOADING = "downloading"
    IDLE = "idle"
    
class BatteryState():
    def __init__(self):
        self.charging = False
        self.level = 0
        
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
            self.system_state = SystemState.BOOTING
            self.docking_state = DockingState.DOCKED
            self.gps_state = GPSState.NO_FIX
            self.cellular_state = CellularState.NO_SIGNAL
            self.imu_state = IMUState.ERROR
            self.downloading_state = DownloadingState.IDLE
            self.battery_state = BatteryState()
            self.leds_manager = LedsManager()
            LedsManagerService._initialized = True
            
    def set_system_state(self, state: SystemState):
        if self.system_state != state:
            self.system_state = state
            self._update_leds()
            
    def set_docking_state(self, state: DockingState):
        if self.docking_state != state:
            self.docking_state = state
            self._update_leds()
            
    def set_gps_state(self, state: GPSState):
        if self.gps_state != state:
            self.gps_state = state
            self._update_leds()
    
    def set_downloading(self, state: DownloadingState):
        if self.downloading_state != state:
            self.downloading_state = state
            self._update_leds()
            
    def set_cellular_state(self, state: CellularState):
        if self.cellular_state != state:
            self.cellular_state = state
            self._update_leds()
            
    def set_imu_state(self, state: IMUState):
        if self.imu_state != state:
            self.imu_state = state
            self._update_leds()
            
    def set_charging(self, charging: int):
        if self.charging != charging:
            self.charging = charging
            self._update_leds()
        
    def _update_leds(self):
        if self.system_state == SystemState.BOOTING:
            self.leds_manager.blink(LEDColor.RED, 1000)
        elif self.system_state == SystemState.MALFUNCTIONING:
            self.leds_manager.turn_on(LEDColor.RED)
        elif self.imu_state == IMUState.ERROR:
            self.leds_manager.turn_on(LEDColor.RED)
        elif self.downloading_state == DownloadingState.DOWNLOADING:
            self.leds_manager.blink(LEDColor.BLUE, 100)
        elif self.docking_state == DockingState.UNDOCKED:
            self.leds_manager.turn_on(LEDColor.RED)
        elif self.gps_state == GPSState.NO_FIX:
            self.leds_manager.blink(LEDColor.RED, 100)
        elif self.imu_state == IMUState.CALIBRATING:
            self.leds_manager.blink(LEDColor.GREEN, 100)
        elif self.cellular_state == CellularState.NO_SIGNAL:
            self.leds_manager.blink(LEDColor.GREEN, 1000)
        elif self.system_state == SystemState.ON:
            self.leds_manager.turn_on(LEDColor.GREEN)
        elif self.battery_state.charging:
            # Blink the LED by battery level: 1000ms (empty) to 100ms (full); solid blue at full charge
            level = self.battery_state.level
            if level >= 100:
                self.leds_manager.turn_on(LEDColor.BLUE)
            else:
                blink_ms = int(1000 - (900 * min(max(level, 0), 100) / 100))
                self.leds_manager.blink(LEDColor.BLUE, blink_ms)
        else:
            self.leds_manager.turn_on(LEDColor.RED)
        self._print_state()
            
    def _print_state(self):
        print(f"{time.ctime(time.time())}: LedsManagerService state: "
              f"system_state={self.system_state}, "
              f"docking_state={self.docking_state}, "
              f"imu_state={self.imu_state}, "
              f"downloading_state={self.downloading_state}, "
              f"gps_state={self.gps_state}, "
              f"cellular_state={self.cellular_state}, "
              f"battery_level={getattr(self.battery_state, 'level', None)}, "
              f"battery_charging={getattr(self.battery_state, 'charging', None)}, "
              f"charging={self.battery_state.charging}, "
              f"level={self.battery_state.level}")