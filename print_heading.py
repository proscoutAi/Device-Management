#!/usr/bin/env python3
"""
Script to print IMU heading every 100ms using IMU_manager.
"""

import time
from IMU_manager import IMUManager

def main():
    # Initialize IMU manager with 10 Hz rate (faster than needed for 100ms reads)
    # This ensures we have fresh data when reading every 100ms
    imu_manager = IMUManager(imu_rate_per_second=10)
    
    print("Starting heading monitor (100ms interval)")
    print("Press Ctrl+C to stop")
    print("-" * 50)
    
    try:
        while True:
            # Get the heading from the IMU data
            heading = imu_manager.imu_data['heading_compensated_deg']
            
            # Print heading with timestamp
            timestamp = time.time()
            print(f"[{time.ctime(timestamp)}] Heading: {heading:.2f}°")
            
            # Wait 100ms (0.1 seconds)
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"\nError: {e}")

if __name__ == "__main__":
    main()






