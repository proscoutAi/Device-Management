import re
import time
from datetime import datetime
import sys
import serial

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)



class GPSManager:
    def __init__(self, port='/dev/ttyGSM1', baudrate=115200):
      try:
        # Open serial connection to GSM multiplexer
        self.ser = serial.Serial(port, baudrate, timeout=2)
        # AT commands to request NMEA data
        self.at_command = [
            'AT+UGRMC?\r\n',
            'AT+UGGGA?\r\n', 
            'AT+UGGLL?\r\n',
            'AT+UGGSV?\r\n'
        ]
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
      except Exception as e:
            print(f"Failed to connect to {port}: {e}")
            return None
    
    
    def send_at_command(self, command):
        """Send AT command and return response"""
        if not self.ser:
            return None
            
        try:
            self.ser.flushInput()
            self.ser.write(f"{command}\r\n".encode())
            
            response = ""
            start_time = time.time()
            
            while time.time() - start_time < 3:
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8', errors='ignore').strip()
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
                    self.gps_data['time_utc'] = f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
                
                # Status
                status = parts[2]
                self.gps_data['fix_status'] = 'Valid Fix' if status == 'A' else 'No Fix'
                
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
                    self.gps_data['date'] = f"{date_str[:2]}/{date_str[2:4]}/{date_str[4:6]}"
                
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
        
        try:
            for command, parser in commands:
                response = self.send_at_command(command)
                if response:
                    nmea_sentence = self.extract_nmea(response)
                    if nmea_sentence:
                        parser(nmea_sentence)
            
            self.gps_data['last_update'] = datetime.now().strftime('%H:%M:%S')
            
        except Exception as e:
            print(f"GPS Manager: Error getting coordinates: {e}")

    
    
    def get_gps_data(self):
        """Get current GPS data"""
        try:
            self.update_gps_data()  # Remove the redundant send_at_command() call
            return self.gps_data
        except Exception as e:
            print(f"GPS Manager: Error getting coordinates: {e}")
            return self.gps_data


gps_manager = GPSManager()

def get_gps_data():
    global gps_manager
    if gps_manager is not None:
        return gps_manager.get_gps_data()
    else:
        print("GPS is not connected retrying")
        gps_manager = GPSManager()