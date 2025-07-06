import time
from datetime import datetime
import sys
import dbus

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

class GPSManager:
    def __init__(self):

        self.bus = None
        self.location_interface = None
        self._connect()
    
    def _connect(self):
        """Establish D-Bus connections"""
        try:
            self.bus = dbus.SystemBus()
            mm = dbus.Interface(
                self.bus.get_object('org.freedesktop.ModemManager1', '/org/freedesktop/ModemManager1'),
                'org.freedesktop.DBus.ObjectManager')
            modems = mm.GetManagedObjects()
            
            
            # Find the first modem and connect to its location interface
            for modem_path in modems:
                print(modem_path)
                if 'org.freedesktop.ModemManager1.Modem' in modems[modem_path]:
                    modem = self.bus.get_object('org.freedesktop.ModemManager1', modem_path)
                    self.location_interface = dbus.Interface(
                        modem, 'org.freedesktop.ModemManager1.Modem.Location')
                    print(f"GPS Manager: Connected to modem {modem_path} (2s updates)")
                    return True
            
            print("GPS Manager: No modems found")
            return False
            
        except Exception as e:
            print(f"GPS Manager: Failed to connect to D-Bus: {e}")
            return False
    
    def get_coordinates(self):

        if not self.location_interface:
            if not self._connect():
                return None
        
        try:
            # Fast location read - GPS updates every 2 seconds automatically
            location_data = self.location_interface.GetLocation()
            
            if not location_data:
                return None
            
            # Initialize GPS data structure
            gps_data = {
                'latitude': None,
                'longitude': None,
                'altitude': None,
                'timestamp': time.time(),
                'speed_kmh': None,
                'heading': None,
                'fix_quality': None,
                'satellites': None,
                'gps_timestamp': None
            }
            
            # Extract coordinates from key 2 (fastest method)
            if 2 in location_data and isinstance(location_data[2], dict):
                coord_data = location_data[2]
                if 'latitude' in coord_data and 'longitude' in coord_data:
                    gps_data['latitude'] = float(coord_data['latitude'])
                    gps_data['longitude'] = float(coord_data['longitude'])
                    if 'altitude' in coord_data:
                        gps_data['altitude'] = float(coord_data['altitude'])
                    if 'utc-time' in coord_data:
                        gps_data['gps_timestamp'] = str(coord_data['utc-time'])
                    
                    # Extract additional data from NMEA if available
                    if 4 in location_data:
                        nmea_data = str(location_data[4])
                        extra_data = self._parse_nmea_extras(nmea_data)
                        gps_data.update(extra_data)
                    
                    return gps_data
            
            # Fallback: parse NMEA data if key 2 not available
            if 4 in location_data:
                nmea_data = str(location_data[4])
                coords = self._parse_nmea_coordinates(nmea_data)
                if coords:
                    gps_data.update(coords)
                    extra_data = self._parse_nmea_extras(nmea_data)
                    gps_data.update(extra_data)
                    return gps_data
            
            return None
            
        except Exception as e:
            print(f"GPS Manager: Error getting coordinates: {e}")
            # Try to reconnect for next call
            self._connect()
            return None
    
    def get_gps_age_seconds(self):
        """Get age of GPS data in seconds"""
        try:
            location_data = self.location_interface.GetLocation()
            if not location_data or 2 not in location_data:
                return None
            
            coord_data = location_data[2]
            if not isinstance(coord_data, dict) or 'utc-time' not in coord_data:
                return 0  # If no timestamp, assume current
            
            utc_time_str = str(coord_data['utc-time'])
            utc_hours = int(utc_time_str[:2])
            utc_minutes = int(utc_time_str[2:4])
            utc_seconds = float(utc_time_str[4:])
            
            import datetime as dt
            now_utc = dt.datetime.utcnow()
            gps_utc = now_utc.replace(hour=utc_hours, minute=utc_minutes, 
                                    second=int(utc_seconds), microsecond=0)
            
            return abs((now_utc - gps_utc).total_seconds())
            
        except Exception as e:
            print(f"GPS Manager: Error checking GPS age: {e}")
            return None
    
    def _parse_nmea_extras(self, nmea_data):
        """Parse speed, heading, satellites from NMEA data"""
        data = {}
        
        for line in nmea_data.split('\n'):
            line = line.strip()
            
            # Parse speed and heading from GPRMC
            if line.startswith('$GPRMC') or line.startswith('$GNRMC'):
                parts = line.split(',')
                if len(parts) >= 9:
                    try:
                        if parts[7]:  # Speed in knots
                            speed_knots = float(parts[7])
                            data['speed_kmh'] = speed_knots * 1.852
                        if parts[8]:  # Course over ground
                            data['heading'] = float(parts[8])
                    except (ValueError, IndexError):
                        pass
            
            # Parse altitude, fix quality, satellites from GPGGA
            elif line.startswith('$GPGGA') or line.startswith('$GNGGA'):
                parts = line.split(',')
                if len(parts) >= 10:
                    try:
                        if parts[9]:  # Altitude
                            data['altitude'] = float(parts[9])
                        if parts[6]:  # Fix quality
                            data['fix_quality'] = int(parts[6])
                        if parts[7]:  # Number of satellites
                            data['satellites'] = int(parts[7])
                    except (ValueError, IndexError):
                        pass
        
        return data
    
    def _parse_nmea_coordinates(self, nmea_data):
        """Parse coordinates from NMEA data (fallback method)"""
        coords = {}
        
        for line in nmea_data.split('\n'):
            line = line.strip()
            
            # Parse GNGNS sentence
            if line.startswith('$GNGNS'):
                parts = line.split(',')
                if len(parts) >= 6:
                    try:
                        if parts[2] and parts[3]:
                            lat_raw = float(parts[2])
                            lat_deg = int(lat_raw / 100)
                            lat_min = lat_raw % 100
                            coords['latitude'] = lat_deg + lat_min / 60
                            if parts[3] == 'S':
                                coords['latitude'] = -coords['latitude']
                        
                        if parts[4] and parts[5]:
                            lon_raw = float(parts[4])
                            lon_deg = int(lon_raw / 100)
                            lon_min = lon_raw % 100
                            coords['longitude'] = lon_deg + lon_min / 60
                            if parts[5] == 'W':
                                coords['longitude'] = -coords['longitude']
                                
                    except (ValueError, IndexError):
                        continue
        
        return coords

# Global GPS manager instance (singleton)
gps_manager = GPSManager()

def get_coordinates():
    """Get current GPS coordinates - fresh every 2 seconds"""
    return gps_manager.get_coordinates()

def get_gps_age():
    """Get age of GPS data in seconds (should be 0-2 seconds)"""
    return gps_manager.get_gps_age_seconds()

def get_detailed_gps_info():
    """Get comprehensive GPS information for sprayer logging"""
    data = get_coordinates()
    
    if data:
        gps_age = get_gps_age()
        print(f"GPS Location Data (2s updates):")
        print(f"  Latitude: {data['latitude']:.6f}°")
        print(f"  Longitude: {data['longitude']:.6f}°")
        print(f"  Altitude: {data['altitude']:.1f}m" if data['altitude'] else "  Altitude: N/A")
        print(f"  Speed: {data['speed_kmh']:.1f} km/h" if data['speed_kmh'] else "  Speed: N/A")
        print(f"  Heading: {data['heading']:.1f}°" if data['heading'] else "  Heading: N/A")
        print(f"  Satellites: {data['satellites']}" if data['satellites'] else "  Satellites: N/A")
        print(f"  GPS Age: {gps_age:.0f}s" if gps_age else "  GPS Age: N/A")
        print(f"  Timestamp: {datetime.fromtimestamp(data['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"lat:{data['latitude']} lon:{data['longitude']}")
    else:
        print("No GPS data available")
    
    return data
