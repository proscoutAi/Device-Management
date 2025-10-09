import re
import time
from datetime import datetime
import sys
import serial
import threading
from threading import Lock

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

class GPSManager_dual:
    def __init__(self, command_port='/dev/ttyAMA1', baudrate=115200):
        try:
            # Direct NMEA data connection for dual band GPS
            self.cmd_ser = serial.Serial(command_port, baudrate, timeout=0.1)
            
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
                'satellite_systems': [],
                'signal_quality': 'Unknown',
                'data_timestamp': time.time()  # Add timestamp for freshness
            }
            
            # Threading for continuous reading
            self.data_lock = Lock()
            self.running = True
            self.reader_thread = threading.Thread(target=self._continuous_read, daemon=True)
            self.reader_thread.start()
            
        except Exception as e:
            print(f"Failed to connect to {command_port}: {e}")
            self.cmd_ser = None
    
    def _continuous_read(self):
        """Continuously read NMEA data in background thread"""
        while self.running and self.cmd_ser:
            try:
                if self.cmd_ser.in_waiting > 0:
                    line = self.cmd_ser.readline().decode('utf-8', errors='ignore').strip()
                    if line and line.startswith('$') and '*' in line:
                        self._parse_nmea_line(line)
                time.sleep(0.01)  # Small delay to prevent CPU overload
            except Exception as e:
                print(f"Error in continuous read: {e}")
                time.sleep(0.1)
    
    def _parse_nmea_line(self, sentence):
        """Parse individual NMEA sentence and update data"""
        with self.data_lock:
            try:
                if 'RMC' in sentence:
                    self.parse_rmc(sentence)
                elif 'GGA' in sentence:
                    self.parse_gga(sentence)
                elif 'GSA' in sentence:
                    self.parse_gsa(sentence)
                elif 'GSV' in sentence:
                    self.parse_gsv(sentence)
                
                # Update timestamp whenever we get new data
                self.gps_data_dual['data_timestamp'] = time.time()
                self.gps_data_dual['last_update'] = datetime.now().strftime('%H:%M:%S')
                
            except Exception as e:
                pass
    
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
    
    def get_gps_data(self):
        """Get current GPS data - now returns immediately cached data"""
        with self.data_lock:
            # Return a copy of the current data
            return self.gps_data_dual.copy()
    
    def get_data_age(self):
        """Get age of GPS data in seconds"""
        with self.data_lock:
            return time.time() - self.gps_data_dual['data_timestamp']
    
    def close(self):
        """Close serial connection and stop thread"""
        self.running = False
        if self.reader_thread and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=1)
        if self.cmd_ser:
            self.cmd_ser.close()

# Global instance
gps_manager_dual = GPSManager_dual()

def get_gps_data_dual():
    global gps_manager_dual
    if gps_manager_dual is not None and gps_manager_dual.cmd_ser:
        return gps_manager_dual.get_gps_data()
    else:
        print("GPS is not connected, retrying...")
        gps_manager_dual = GPSManager_dual()
        return gps_manager_dual.get_gps_data() if gps_manager_dual and gps_manager_dual.cmd_ser else None

def get_gps_data_age():
    """Get age of dual band GPS data"""
    global gps_manager_dual
    if gps_manager_dual is not None:
        return gps_manager_dual.get_data_age()
    return None

# Test function
if __name__ == "__main__":
    print("Testing Threaded Dual Band GPS Manager...")
    try:
        while True:
            data = get_gps_data_dual()
            age = get_gps_data_age()
            if data:
                print(f"\n=== GPS Data Update ===")
                print(f"Status: {data['fix_status']}")
                print(f"Position: {data['latitude']:.6f}, {data['longitude']:.6f}")
                print(f"Data Age: {age:.2f}s")
                print(f"Updated: {data['last_update']}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping GPS test...")
        if gps_manager_dual:
            gps_manager_dual.close()