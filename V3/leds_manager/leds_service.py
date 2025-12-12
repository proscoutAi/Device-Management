import os
import socket

from button_led_manager import ButtonLEDManager, LEDColor


class LEDCommand:
    """Parse LED command string into color, action, and speed."""
    
    def __init__(self, command):
        # Map lowercase color strings to LEDColor enum values
        leds_dict = {
            "red": LEDColor.RED,
            "green": LEDColor.GREEN,
            "blue": LEDColor.BLUE,
        }
        
        params = command.split(":")
        if len(params) == 1:
            action = params[0].lower().strip()
            if action not in ["off"]:
                raise ValueError(f"Invalid color: {params[0]}. Must be one of: {list(leds_dict.keys())}")
            self.led_color = None
            self.action = action
            self.speed = None
        elif len(params) == 2:
            color_str = params[0].lower().strip()
            if color_str not in leds_dict:
                raise ValueError(f"Invalid color: {params[0]}. Must be one of: {list(leds_dict.keys())}")
            self.led_color = leds_dict[color_str]
            action = params[1].lower().strip()
            if action not in ["on", "blink"]:
                raise ValueError(f"Invalid action: {params[1]}. Must be one of: on, blink")
            self.action = action
            self.speed = None
        elif len(params) == 3:
            color_str = params[0].lower().strip()
            if color_str not in leds_dict:
                raise ValueError(f"Invalid color: {params[0]}. Must be one of: {list(leds_dict.keys())}")
            self.led_color = leds_dict[color_str]
            action = params[1].lower().strip()
            if action not in ["on", "blink"]:
                raise ValueError(f"Invalid action: {params[1]}. Must be one of: on, blink")
            self.action = params[1].lower().strip()
            try:
                self.speed = int(params[2].strip())
            except ValueError:
                self.speed = None
        else:
            raise ValueError(f"Invalid command format: {command}. Expected format: 'color[:action[:speed]]'")

sock_path = "/tmp/led.sock"
if os.path.exists(sock_path):
    os.remove(sock_path)

server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(sock_path)
server.listen(5)

led_manager = ButtonLEDManager()
led_manager.blink(LEDColor.RED, 500)

print("LED service started, waiting for clients...")

while True:
    conn, _ = server.accept()
    
    try:
        cmd = conn.recv(1024).decode().strip()
        
        if cmd:
            print(f"Received command: {cmd}")
            
            try:
                led_command = LEDCommand(cmd)
                if led_command.action == "on":
                    led_manager.turn_on(led_command.led_color)
                elif led_command.action == "blink":
                    if led_command.speed is None:
                        print(f"Error: Speed required for blink action")
                    else:
                        led_manager.blink(led_command.led_color, led_command.speed)
                elif led_command.action == "off":
                    led_manager.turn_off()
                elif led_command.action is None:
                    # Single color parameter - turn on that color
                    led_manager.turn_on(led_command.led_color)
                else:
                    print(f"Error: Unknown action: {led_command.action}")
            except Exception as e:
                print(f"Error processing command '{cmd}': {e}")
    except Exception as e:
        print(f"Error handling connection: {e}")
    finally:
        # Close connection after processing the command
        conn.close()