"""
Debug script for ButtonLEDManager.

Provides an interactive menu to test LED operations.
"""
import sys
import time

from button_led_manager import ButtonLEDManager, LEDColor


def print_menu():
    """Print the main menu."""
    print("\n" + "="*50)
    print("Button LED Manager - Debug Menu")
    print("="*50)
    print("1. Turn on RED LED")
    print("2. Turn on GREEN LED")
    print("3. Turn on BLUE LED")
    print("4. Blink RED LED")
    print("5. Blink GREEN LED")
    print("6. Blink BLUE LED")
    print("7. Turn off current LED")
    print("8. Cleanup and exit")
    print("="*50)


def get_color_choice():
    """Get LED color choice from user."""
    print("\nSelect LED color:")
    print("1. RED")
    print("2. GREEN")
    print("3. BLUE")
    
    choice = input("Enter choice (1-3): ").strip()
    
    color_map = {
        '1': LEDColor.RED,
        '2': LEDColor.GREEN,
        '3': LEDColor.BLUE
    }
    
    return color_map.get(choice)


def get_speed():
    """Get blink speed from user."""
    while True:
        try:
            speed = input("Enter blink speed in milliseconds (e.g., 500): ").strip()
            speed_ms = int(speed)
            if speed_ms <= 0:
                print("Speed must be greater than 0")
                continue
            return speed_ms
        except ValueError:
            print("Invalid input. Please enter a positive integer.")


def main():
    """Main debug function."""
    print("Initializing ButtonLEDManager...")
    
    try:
        led_manager = ButtonLEDManager()
        print("✓ ButtonLEDManager initialized successfully")
        print(f"  Available LEDs: RED (GPIO {LEDColor.RED.value}), "
              f"GREEN (GPIO {LEDColor.GREEN.value}), "
              f"BLUE (GPIO {LEDColor.BLUE.value})")
    except Exception as e:
        print(f"✗ Failed to initialize ButtonLEDManager: {e}")
        print("Make sure you're running on a Raspberry Pi with gpiozero installed")
        sys.exit(1)
    
    try:
        while True:
            print_menu()
            choice = input("Enter your choice (1-8): ").strip()
            
            if choice == '1':
                print("\nTurning on RED LED...")
                led_manager.turn_on(LEDColor.RED)
                print("✓ RED LED is now ON")
                
            elif choice == '2':
                print("\nTurning on GREEN LED...")
                led_manager.turn_on(LEDColor.GREEN)
                print("✓ GREEN LED is now ON")
                
            elif choice == '3':
                print("\nTurning on BLUE LED...")
                led_manager.turn_on(LEDColor.BLUE)
                print("✓ BLUE LED is now ON")
                
            elif choice == '4':
                speed_ms = get_speed()
                print(f"\nBlinking RED LED at {speed_ms}ms intervals...")
                led_manager.blink(LEDColor.RED, speed_ms)
                print("✓ RED LED is now blinking")
                
            elif choice == '5':
                speed_ms = get_speed()
                print(f"\nBlinking GREEN LED at {speed_ms}ms intervals...")
                led_manager.blink(LEDColor.GREEN, speed_ms)
                print("✓ GREEN LED is now blinking")
                
            elif choice == '6':
                speed_ms = get_speed()
                print(f"\nBlinking BLUE LED at {speed_ms}ms intervals...")
                led_manager.blink(LEDColor.BLUE, speed_ms)
                print("✓ BLUE LED is now blinking")
                
            elif choice == '7':
                print("\nTurning off current LED...")
                led_manager.turn_off()
                print("✓ LED turned off")
                
            elif choice == '8':
                print("\nCleaning up and exiting...")
                led_manager.cleanup()
                print("✓ Cleanup complete")
                break
                
            else:
                print("\n✗ Invalid choice. Please enter a number between 1-8.")
            
            # Small delay for better UX
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Cleaning up...")
        led_manager.cleanup()
        print("✓ Cleanup complete")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("Cleaning up...")
        led_manager.cleanup()
        sys.exit(1)


if __name__ == '__main__':
    main()
