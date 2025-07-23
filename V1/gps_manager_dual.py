import re
import time
from datetime import datetime
import sys
import serial

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

class GPSManager_dual:
    def __init__(self, command_port='/dev/ttyAMA1', baudrate=115200):
        try:
            # Direct NMEA data connection for dual band GPS
            self.cmd_ser = serial.Serial(command_port, baudrate, timeout=2)
            
            self.gps_data_dual = {
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
                'pdop': 0.0,
                'vdop': 0.0,
                'time_utc': 'N/A',
                'date': 'N/A',
                'last_update': 'N/A',
                'satellite_systems': [],  # Track which systems are active
                'signal_quality': 'Unknown'
            }
            
        except Exception as e:
            print(f"Failed to connect to {command_port}: {e}")
            return None
    
    def read_nmea_sentences(self):
        """Read multiple NMEA sentences from dual band GPS"""
        if not self.cmd_ser:
            return []
            
        try:
            sentences = []
            start_time = time.time()
            
            # Read for up to 3 seconds to get a good sample of NMEA data
            while time.time() - start_time < 3:
                if self.cmd_ser.in_waiting > 0:
                    line = self.cmd_ser.readline().decode('utf-8', errors='ignore').strip()
                    if line and line.startswith('$') and '*' in line:
                        sentences.append(line)
                        # Stop after getting a good sample
                        if len(sentences) >= 15:
                            break
                time.sleep(0.01)
            
            return sentences
        except Exception as e:
            print(f"Error reading NMEA: {e}")
            return []
    
    def parse_rmc(self, nmea_sentence):
        """Parse RMC sentence (works with GPRMC, GNRMC, GLRMC, etc.)"""
        try:
            parts = nmea_sentence.split(',')
            if len(parts) >= 12:
                # Time
                time_str = parts[1]
                if len(time_str) >= 6:
                    self.gps_data_dual['time_utc'] = f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
                
                # Status
                status = parts[2]
                self.gps_data_dual['fix_status'] = 'Valid Fix' if status == 'A' else 'No Fix'
                
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
                        
                        self.gps_data_dual['latitude'] = lat_deg
                        self.gps_data_dual['longitude'] = lon_deg
                
                # Speed
                speed_str = parts[7]
                if speed_str:
                    self.gps_data_dual['speed_knots'] = float(speed_str)
                    self.gps_data_dual['speed_kmh'] = float(speed_str) * 1.852
                
                # Course
                course_str = parts[8]
                if course_str:
                    self.gps_data_dual['course'] = float(course_str)
                
                # Date
                date_str = parts[9]
                if len(date_str) >= 6:
                    self.gps_data_dual['date'] = f"20{date_str[4:6]}-{date_str[2:4]}-{date_str[:2]}"
                
        except Exception as e:
            pass

    def parse_gga(self, nmea_sentence):
        """Parse GGA sentence (works with GPGGA, GNGGA, etc.)"""
        try:
            parts = nmea_sentence.split(',')
            if len(parts) >= 15:
                # Fix quality
                fix_quality = parts[6]
                if fix_quality:
                    quality_map = {
                        '0': 'No Fix',
                        '1': 'GPS Fix',
                        '2': 'DGPS Fix',
                        '3': 'PPS Fix',
                        '4': 'RTK Fix',
                        '5': 'Float RTK',
                        '6': 'Estimated',
                        '7': 'Manual',
                        '8': 'Simulation'
                    }
                    self.gps_data_dual['signal_quality'] = quality_map.get(fix_quality, 'Unknown')
                
                # Satellites used
                sats_str = parts[7]
                if sats_str:
                    self.gps_data_dual['satellites_used'] = int(sats_str)
                
                # HDOP
                hdop_str = parts[8]
                if hdop_str:
                    self.gps_data_dual['hdop'] = float(hdop_str)
                
                # Altitude
                alt_str = parts[9]
                if alt_str:
                    self.gps_data_dual['altitude'] = float(alt_str)
                    
        except Exception as e:
            pass
    
    def parse_gsa(self, nmea_sentence):
        """Parse GSA sentence for DOP values and fix type"""
        try:
            parts = nmea_sentence.split(',')
            if len(parts) >= 18:
                # Fix type
                fix_type = parts[2]
                if fix_type == '1':
                    self.gps_data_dual['fix_status'] = 'No Fix'
                elif fix_type == '2':
                    self.gps_data_dual['fix_status'] = '2D Fix'
                elif fix_type == '3':
                    self.gps_data_dual['fix_status'] = '3D Fix'
                
                # PDOP, HDOP, VDOP
                if parts[15]:  # PDOP
                    self.gps_data_dual['pdop'] = float(parts[15])
                if parts[16]:  # HDOP
                    self.gps_data_dual['hdop'] = float(parts[16])
                if parts[17].split('*')[0]:  # VDOP (remove checksum)
                    self.gps_data_dual['vdop'] = float(parts[17].split('*')[0])
                    
        except Exception as e:
            pass
    
    def parse_gsv(self, nmea_sentence):
        """Parse GSV sentence for satellite information"""
        try:
            parts = nmea_sentence.split(',')
            if len(parts) >= 4:
                # Track satellite systems
                sentence_type = parts[0]
                if sentence_type.startswith('$GP'):
                    system = 'GPS'
                elif sentence_type.startswith('$GL'):
                    system = 'GLONASS'
                elif sentence_type.startswith('$GA'):
                    system = 'Galileo'
                elif sentence_type.startswith('$GB'):
                    system = 'BeiDou'
                elif sentence_type.startswith('$GN'):
                    system = 'Multi-GNSS'
                else:
                    system = 'Unknown'
                
                if system not in self.gps_data_dual['satellite_systems']:
                    self.gps_data_dual['satellite_systems'].append(system)
                
                # Satellites in view (only update on first GSV message)
                if parts[2] == '1':  # First message of the sequence
                    sats_str = parts[3]
                    if sats_str:
                        self.gps_data_dual['satellites_view'] = int(sats_str)
                    
        except Exception as e:
            pass
    
    def update_gps_data(self):
        """Update GPS data from dual band GPS device"""
        # Clear satellite systems for fresh update
        self.gps_data_dual['satellite_systems'] = []
        
        # Read NMEA sentences
        sentences = self.read_nmea_sentences()
        
        # Parse each sentence
        for sentence in sentences:
            try:
                if 'RMC' in sentence:
                    self.parse_rmc(sentence)
                elif 'GGA' in sentence:
                    self.parse_gga(sentence)
                elif 'GSA' in sentence:
                    self.parse_gsa(sentence)
                elif 'GSV' in sentence:
                    self.parse_gsv(sentence)
            except Exception as e:
                continue
        
        self.gps_data_dual['last_update'] = datetime.now().strftime('%H:%M:%S')
    
    def get_gps_data(self):
        """Get current GPS data"""
        try:
            self.update_gps_data()
            return self.gps_data_dual
        except Exception as e:
            print(f"GPS Manager: Error getting coordinates: {e}")
            return self.gps_data_dual
    
    def close(self):
        """Close serial connection"""
        if self.cmd_ser:
            self.cmd_ser.close()

# Global instance
gps_manager_dual = GPSManager_dual()

def get_gps_data_dual():
    global gps_manager_dual
    if gps_manager_dual is not None:
        return gps_manager_dual.get_gps_data()
    else:
        print("GPS is not connected, retrying...")
        gps_manager_dual = GPSManager_dual()
        return gps_manager_dual.get_gps_data() if gps_manager_dual else None

# Test function
if __name__ == "__main__":
    print("Testing Dual Band GPS Manager...")
    try:
        while True:
            data = get_gps_data_dual()
            if data:
                print(f"\n=== GPS Data Update ===")
                print(f"Status: {data['fix_status']}")
                print(f"Position: {data['latitude']:.6f}, {data['longitude']:.6f}")
                print(f"Altitude: {data['altitude']:.1f}m")
                print(f"Speed: {data['speed_kmh']:.1f} km/h")
                print(f"Satellites: {data['satellites_used']} used, {data['satellites_view']} visible")
                print(f"HDOP: {data['hdop']:.2f}")
                print(f"Systems: {', '.join(data['satellite_systems'])}")
                print(f"Quality: {data['signal_quality']}")
                print(f"Updated: {data['last_update']}")
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nStopping GPS test...")
        if gps_manager_dual:
            gps_manager_dual.close()