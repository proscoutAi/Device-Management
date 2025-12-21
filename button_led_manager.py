"""
Button LED Manager - Singleton class to handle RGB LEDs on button.

This class manages red, blue, and green LEDs connected to GPIO pins.
LEDs are active LOW (turn on with LOW signal, turn off with HIGH).
Only one LED can be active at a time.
"""
import threading
import time
from enum import Enum

from gpiozero import LED


class LEDColor(Enum):
    """Enum for LED colors with their GPIO pin values."""
    RED = 16
    GREEN = 20
    BLUE = 21


class ButtonLEDManager:
    """
    Singleton class to manage button LEDs.
    
    Manages red, blue, and green LEDs with the following features:
    - Only one LED can be active at a time
    - LEDs are active LOW (LOW = ON, HIGH = OFF)
    - Supports solid ON and blinking modes
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """
        Create or return the singleton instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ButtonLEDManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """
        Initialize the LED manager with GPIO pins from LEDColor enum.
        """
        if self._initialized:
            return
        
        # Initialize LEDs dictionary - GPIO pins come from enum values
        self.leds = {}
        
        # Initialize LEDs as output with active_high=False (LOW = ON)
        try:
            for color in LEDColor:
                gpio_pin = color.value
                self.leds[color] = LED(gpio_pin, active_high=False)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize LEDs: {e}")
        
        # Track current LED state
        self.current_led = None  # Will store the LED object that is currently on/blinking
        self.blink_thread = None
        self.blink_event = None
        self.blink_lock = threading.Lock()
        
        # Turn on green LED as default state
        self._turn_on_green_default()
        
        self._initialized = True
    
    def _turn_on_green_default(self):
        """Turn on green LED as default/standby state."""
        try:
            # Turn off all LEDs first
            for led in self.leds.values():
                led.off()  # off() sets HIGH when active_high=False
            # Turn on green LED (default state)
            self.leds[LEDColor.GREEN].on()  # on() sets LOW when active_high=False
        except Exception as e:
            print(f"{time.ctime(time.time())}:ButtonLEDManager: Error setting green LED default: {e}")
    
    def _turn_off_green(self):
        """Turn off green LED."""
        try:
            self.leds[LEDColor.GREEN].off()  # off() sets HIGH when active_high=False
        except Exception as e:
            print(f"{time.ctime(time.time())}:ButtonLEDManager: Error turning off green LED: {e}")
    
    def _get_led_by_color(self, color: LEDColor):
        """
        Get the LED object for the given color.
        
        Args:
            color (LEDColor): The color enum value
            
        Returns:
            LED: The gpiozero LED object
        """
        if color not in self.leds:
            raise ValueError(f"Invalid LED color: {color}")
        return self.leds[color]
    
    def turn_on(self, color: LEDColor):
        """
        Turn on a specific LED color.
        
        Only one LED can be on at a time. If another LED is currently on/blinking,
        it will be turned off first. Green LED will be turned off before activating.
        
        Args:
            color (LEDColor): The color enum value to turn on
        """
        with self.blink_lock:
            # Stop any blinking
            self._stop_blinking()
            
            # Turn off current LED if any
            if self.current_led is not None:
                self.current_led.off()  # Sets HIGH when active_high=False
            
            if color == LEDColor.GREEN:
                return
            
            # Turn off green LED before turning on requested LED
            self._turn_off_green()
            
            # Turn on the requested LED
            led = self._get_led_by_color(color)
            led.on()  # Sets LOW when active_high=False
            
            # Update current state
            self.current_led = led
    
    def blink(self, color: LEDColor, speed_ms: int):
        """
        Blink a specific LED color at the specified speed.
        
        Only one LED can be active at a time. If another LED is currently on/blinking,
        it will be turned off first. Green LED will be turned off before starting blink.
        
        Args:
            color (LEDColor): The color enum value to blink
            speed_ms (int): Blink speed in milliseconds
        """
        if speed_ms <= 0:
            raise ValueError("Speed must be greater than 0 milliseconds")
        
        with self.blink_lock:
            # Stop any existing blinking
            self._stop_blinking()
            
            # Turn off current LED if any
            if self.current_led is not None:
                self.current_led.off()
            
            # Turn off green LED before starting blink
            self._turn_off_green()
            
            # Get the LED for the requested color
            led = self._get_led_by_color(color)
            self.current_led = led
            
            # Create event to control blinking
            self.blink_event = threading.Event()
            
            # Start blinking thread
            self.blink_thread = threading.Thread(
                target=self._blink_loop,
                args=(led, speed_ms),
                daemon=True
            )
            self.blink_thread.start()
    
    def _blink_loop(self, led: LED, speed_ms: int):
        """
        Internal method to handle LED blinking in a separate thread.
        
        Args:
            led (LED): The gpiozero LED object to blink
            speed_ms (int): Blink speed in milliseconds
        """
        try:
            while not self.blink_event.is_set():
                led.on()  # Turn on (LOW)
                if self.blink_event.wait(timeout=speed_ms / 1000.0):
                    break  # Event was set, exit loop
                
                led.off()  # Turn off (HIGH)
                if self.blink_event.wait(timeout=speed_ms / 1000.0):
                    break  # Event was set, exit loop
        except Exception as e:
            print(f"{time.ctime(time.time())}:ButtonLEDManager: Error in blink loop: {e}")
        finally:
            # Ensure LED is turned off when blinking stops
            led.off()
    
    def _stop_blinking(self):
        """Stop any active blinking."""
        if self.blink_event is not None:
            self.blink_event.set()
            self.blink_event = None
        
        if self.blink_thread is not None:
            # Wait for thread to finish (with timeout)
            self.blink_thread.join(timeout=1.0)
            self.blink_thread = None
    
    def turn_off(self):
        """
        Turn off the currently active LED and turn on green LED as default.
        
        If an LED is blinking, the blinking will be stopped and the LED turned off.
        Green LED will be turned on as the default/standby state.
        """
        with self.blink_lock:
            # Stop blinking if active
            self._stop_blinking()
            
            # Turn off current LED if any
            if self.current_led is not None:
                self.current_led.off()  # Sets HIGH when active_high=False
                self.current_led = None
            
            # Turn on green LED as default state
            self._turn_on_green_default()
    
    def cleanup(self):
        """
        Clean up resources and turn on green LED as default state.
        
        Should be called when shutting down the application.
        """
        with self.blink_lock:
            self._stop_blinking()
            self._turn_on_green_default()
            self.current_led = None
