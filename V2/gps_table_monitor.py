import serial
import time
import re
import sys
import os
import math
from datetime import datetime

class GPSTableMonitor:
    def __init__(self, port='/dev/ttyGSM0', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.gps_data = {
            'fix_status': 'No Fix',
            'latitude': 0.0,
            'longitude': 0.0,
            'altitude': 0.0,
            'speed_knots': 0.0,
            'speed_kmh': 0.0,
            'course': 0.0,
            'satellites_used': 0,
            'satellites_view': 0,
            'hdop': 0.0,
            'time_utc': 'N/A',
            'date': 'N/A',
            'last_update': 'N/A'
        }
        
    def connect(self):
        """Connect to GPS device"""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=2
            )
            return True
        except Exception as e:
            print(f"Failed to connect to {self.port}: {e}")
            return False
    
    def send_at_command(self, command):
        """Send AT command and return response"""
        if not self.serial_conn:
            return None
            
        try:
            self.serial_conn.flushInput()
            self.serial_conn.write(f"{command}\r\n".encode())
            
            response = ""
            start_time = time.time()
            
            while time.time() - start_time < 3:
                if self.serial_conn.in_waiting > 0:
                    line = self.serial_conn.readline().decode('utf-8', errors='>
                    if line:
                        response += line + "\n"
                        if line == "OK" or line.startswith("ERROR"):
                            break
                time.sleep(0.01)
            
            return response
        except Exception as e:
            return None

        
    def extract_nmea(self, at_response):
        """Extract NMEA sentence from AT response"""
        if not at_response:
            return None
        
        nmea_pattern = r'\$G[PN][A-Z]{3},[^*]*\*[A-F0-9]{2}'
        match = re.search(nmea_pattern, at_response)
        return match.group(0) if match else None
    
    def parse_rmc(self, nmea_sentence):
        """Parse RMC sentence"""
        try:
            parts = nmea_sentence.split(',')
            if len(parts) >= 12:
                # Time
                time_str = parts[1]
                if len(time_str) >= 6:
                    self.gps_data['time_utc'] = f"{time_str[:2]}:{time_str[2:4]>
                
                # Status
                status = parts[2]
                self.gps_data['fix_status'] = 'Valid Fix' if status == 'A' else>
                
                # Position
                if status == 'A':
                    lat_str = parts[3]
                    lat_dir = parts[4]
                    lon_str = parts[5]
                    lon_dir = parts[6]
                    
                    if lat_str and lon_str:
                        # Convert DDMM.MMMM to decimal degrees
                        lat_deg = float(lat_str[:2]) + float(lat_str[2:]) / 60
                        if lat_dir == 'S':
                            lat_deg = -lat_deg
                                                    
                        lon_deg = float(lon_str[:3]) + float(lon_str[3:]) / 60
                        if lon_dir == 'W':
                            lon_deg = -lon_deg
                        
                        self.gps_data['latitude'] = lat_deg
                        self.gps_data['longitude'] = lon_deg
                
                # Speed
                speed_str = parts[7]
                if speed_str:
                    self.gps_data['speed_knots'] = float(speed_str)
                    self.gps_data['speed_kmh'] = float(speed_str) * 1.852
                
                # Course
                course_str = parts[8]
                if course_str:
                    self.gps_data['course'] = float(course_str)
                
                # Date
                date_str = parts[9]
                if len(date_str) >= 6:
                    self.gps_data['date'] = f"{date_str[:2]}/{date_str[2:4]}/{d>
                
        except Exception as e:
            pass
    
    def parse_gga(self, nmea_sentence):
        """Parse GGA sentence"""
        try:
            parts = nmea_sentence.split(',')
            if len(parts) >= 15:
                # Satellites used
                sats_str = parts[7]
                if sats_str:
                    self.gps_data['satellites_used'] = int(sats_str)
                                    
                # HDOP
                hdop_str = parts[8]
                if hdop_str:
                    self.gps_data['hdop'] = float(hdop_str)
                
                # Altitude
                alt_str = parts[9]
                if alt_str:
                    self.gps_data['altitude'] = float(alt_str)
                    
        except Exception as e:
            pass
    
    def parse_gsv(self, nmea_sentence):
        """Parse GSV sentence"""
        try:
            parts = nmea_sentence.split(',')
            if len(parts) >= 4:
                # Satellites in view
                sats_str = parts[3]
                if sats_str:
                    self.gps_data['satellites_view'] = int(sats_str)
                    
        except Exception as e:
            pass
    
    def update_gps_data(self):
        """Update GPS data from device"""
        commands = [
            ('AT+UGRMC?', self.parse_rmc),
            ('AT+UGGGA?', self.parse_gga),
            ('AT+UGGSV?', self.parse_gsv)
        ]
        
        for command, parser in commands:
                   response = self.send_at_command(command)
            if response:
                nmea_sentence = self.extract_nmea(response)
                if nmea_sentence:
                    parser(nmea_sentence)
        
        self.gps_data['last_update'] = datetime.now().strftime('%H:%M:%S')
    
    def clear_screen(self):
        """Clear terminal screen"""
        os.system('clear' if os.name == 'posix' else 'cls')
    
    def display_table(self):
        """Display GPS data in table format"""
        self.clear_screen()
        
        print("=" * 80)
        print("          SARA-R520M10 GPS Monitor - Press Ctrl+C to Exit")
        print("=" * 80)
        print()
        
        # Status section
        print("┌─ GPS STATUS ──────────────────────────────────────────────────>
        print(f"│ Fix Status     : {self.gps_data['fix_status']:<20} │ Last Upd>
        print(f"│ Satellites Used: {self.gps_data['satellites_used']:<20} │ In >
        print(f"│ HDOP          : {self.gps_data['hdop']:<20.2f} │ Quality    :>
        print("└───────────────────────────────────────────────────────────────>
        print()
        
        # Position section
        print("┌─ POSITION ────────────────────────────────────────────────────>
        print(f"│ Latitude       : {self.gps_data['latitude']:<20.8f} │ ({self.>
        print(f"│ Longitude      : {self.gps_data['longitude']:<20.8f} │ ({self>
        print(f"│ Altitude       : {self.gps_data['altitude']:<20.1f} │ meters >
        print("└───────────────────────────────────────────────────────────────>
        print()
        
        # Movement section
        print("┌─ MOVEMENT ────────────────────────────────────────────────────>
        print(f"│ Speed (knots)  : {self.gps_data['speed_knots']:<20.2f} │ Spee>
        print(f"│ Course         : {self.gps_data['course']:<20.1f} │ Direction>
        print("└───────────────────────────────────────────────────────────────>
        print()
        
        # Time section
        print("┌─ TIME ────────────────────────────────────────────────────────>
        print(f"│ UTC Time       : {self.gps_data['time_utc']:<20} │ Date      >
        print("└───────────────────────────────────────────────────────────────>
        print()
        
        # Raw data section
        print("┌─ RAW DATA ────────────────────────────────────────────────────>
        print(f"│ Latest RMC: AT+UGRMC? (Run this command to see raw NMEA data)>
        print(f"│ Device    : {self.port:<20} │ Baudrate    : {self.baudrate:<2>
        print("└───────────────────────────────────────────────────────────────>
        
        print("\n[Updating every 2 seconds...]")
    
    def deg_to_dms(self, deg, coord_type):
        """Convert decimal degrees to degrees, minutes, seconds"""
        if deg == 0:
            return "N/A"
        
        abs_deg = abs(deg)
        d = int(abs_deg)
        m = int((abs_deg - d) * 60)
        s = ((abs_deg - d) * 60 - m) * 60
        
        if coord_type == 'lat':
            dir_char = 'N' if deg >= 0 else 'S'
        else:
            dir_char = 'E' if deg >= 0 else 'W'
            
        return f"{d:02d}°{m:02d}'{s:04.1f}\"{dir_char}"
    
    def course_to_direction(self, course):
        """Convert course degrees to compass direction"""
        if course == 0:
            return "N/A"
        
        directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                     "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        
        index = int((course + 11.25) / 22.5) % 16
        return directions[index]
    
    def monitor(self):
        """Main monitoring loop"""
        if not self.connect():
            return
        
        print("Starting GPS monitor...")
        print("Connecting to GPS device...")
        
        try:
            while True:
                self.update_gps_data()
                self.display_table()
                time.sleep(2)
                
        except KeyboardInterrupt:
            print("\n\nGPS monitor stopped.")
        finally:
            if self.serial_conn:
                self.serial_conn.close()

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='GPS Table Monitor for SARA-R5>
    parser.add_argument('--port', default='/dev/ttyGSM0', help='GPS device port>
    parser.add_argument('--baudrate', type=int, default=115200, help='Baud rate>
    args = parser.parse_args()
    
    monitor = GPSTableMonitor(port=args.port, baudrate=args.baudrate)
    monitor.monitor()

if __name__ == "__main__":
    main()