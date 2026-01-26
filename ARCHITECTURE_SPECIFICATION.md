# Device Management System - Architecture & Workflow Specification

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Threading Model](#threading-model)
4. [Component Details](#component-details)
5. [Data Flow](#data-flow)
6. [Error Handling & Recovery](#error-handling--recovery)
7. [Configuration](#configuration)
8. [Calling Routines](#calling-routines)

---

## System Overview

The Device Management system is a multi-threaded Python application running on Raspberry Pi Zero that:
- Collects sensor data (GPS, IMU, Flow Meter, Camera)
- Monitors device state (docking, battery, cellular connectivity)
- Batches and uploads data to cloud functions
- Handles offline data storage and retry
- Provides visual feedback via LED status indicators

### Key Characteristics
- **Multi-threaded**: Uses Python `threading` module for concurrent operations
- **Event-driven**: Responds to sensor events and state changes
- **Fault-tolerant**: Implements health monitoring and automatic recovery
- **Offline-capable**: Stores data locally when network is unavailable

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Main Thread                               │
│  (main.py) - Keeps application alive, handles shutdown          │
└────────────────────────────┬──────────────────────────────────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
        ┌───────▼────────┐      ┌─────────▼────────┐
        │ DockingManager │      │   Session Class  │
        │   (docking.py)  │      │   (session.py)   │
        └───────┬────────┘      └─────────┬────────┘
                │                         │
                │                         ├─────────────────┐
                │                         │                 │
        ┌───────▼────────┐      ┌─────────▼────────┐  ┌────▼──────┐
        │ Monitor Thread  │      │  Session Thread  │  │ Upload   │
        │  (daemon)       │      │  (main loop)     │  │ Thread   │
        └────────────────┘      └─────────┬────────┘  │(daemon)  │
                                           │            └────┬─────┘
                                           │                 │
        ┌──────────────────────────────────┼─────────────────┼──────────────┐
        │                                  │                 │              │
┌───────▼────────┐  ┌───────────▼──┐  ┌──▼──────┐  ┌──────▼──────┐  ┌────▼────┐
│ GPSManager     │  │ IMUManager   │  │ Flow    │  │ CloudFunc    │  │ LED     │
│ (gps_manager)  │  │ (IMU_manager)│  │ Meter   │  │ Client       │  │ Service │
└───────┬────────┘  └───────┬──────┘  └────┬────┘  └──────┬───────┘  └─────────┘
        │                   │               │              │
┌───────▼────────┐  ┌───────▼──────┐  ┌────▼────┐  ┌──────▼────────┐
│ Reader Thread │  │ Update Thread│  │ Polling │  │ Offline Upload │
│  (daemon)     │  │  (daemon)    │  │ Thread  │  │ Thread         │
└───────────────┘  └──────────────┘  └─────────┘  │  (daemon)      │
                                                   └────────────────┘
```

---

## Threading Model

### Thread Hierarchy

#### 1. **Main Thread** (`main.py`)
- **Type**: Main execution thread
- **Purpose**: Application entry point, keeps process alive
- **Lifecycle**: Runs until application termination
- **Responsibilities**:
  - Initialize LED manager service
  - Start DockingManager
  - Create and start Session
  - Handle graceful shutdown (KeyboardInterrupt, exceptions)

#### 2. **DockingManager Monitor Thread** (`docking.py`)
- **Type**: Daemon thread
- **Purpose**: Monitor GPIO pin 13 for docking state changes
- **Lifecycle**: Started by `DockingManager.run()`, runs until `monitor_active = False`
- **Responsibilities**:
  - Poll GPIO pin 13 state (HIGH = DOCKED, LOW = UNDOCKED)
  - Update LED service with docking state
  - Use `wait_for_active()` / `wait_for_inactive()` for efficient polling

#### 3. **Session Thread** (`session.py`)
- **Type**: Non-daemon thread (created by `Session.start()`)
- **Purpose**: Main data collection loop
- **Lifecycle**: Started by `Session.start()`, runs while `self.running = True`
- **Responsibilities**:
  - Collect GPS, IMU, Flow Meter, Camera data
  - Batch data into payloads
  - Trigger uploads via ThreadPoolExecutor
  - Monitor sensor health (GPS, IMU)
  - Handle WiFi download-only mode

#### 4. **GPS Reader Thread** (`gps_manager.py`)
- **Type**: Daemon thread
- **Purpose**: Continuously read NMEA sentences from serial port
- **Lifecycle**: Started when `GPSManager` is initialized, runs while `self.running = True`
- **Responsibilities**:
  - Read from `/dev/ttyACM0` serial port
  - Parse NMEA sentences (RMC, GGA, GSA, GSV, ZDA)
  - Update GPS data dictionary with thread-safe locks
  - Update `data_timestamp` on each NMEA sentence

#### 5. **IMU Update Thread** (`IMU_manager.py`)
- **Type**: Daemon thread
- **Purpose**: Continuously read IMU sensor data (accelerometer, gyroscope, magnetometer)
- **Lifecycle**: Started when `IMUManager` is initialized, runs continuously
- **Responsibilities**:
  - Read from I2C sensors (LSM6DSL at 0x6A, MMC5983MA at 0x30)
  - Calculate tilt-compensated heading
  - Buffer IMU readings in `imu_buffer` (thread-safe with locks)
  - Update LED service with IMU state

#### 6. **Flow Meter Polling Thread** (`flow_meter.py`)
- **Type**: Daemon thread
- **Purpose**: Monitor GPIO pin 5 for flow meter pulses
- **Lifecycle**: Started by `setup_flow_meter()`, runs continuously
- **Responsibilities**:
  - Poll GPIO pin 5 for state changes (pulses)
  - Increment global `flow_counter` (thread-safe with locks)
  - Handle debouncing and edge detection

#### 7. **Offline Upload Thread** (`upload.py`)
- **Type**: Daemon thread
- **Purpose**: Upload stored offline data files when connection is restored
- **Lifecycle**: Started when `CloudFunctionClient` is initialized, runs continuously
- **Responsibilities**:
  - Scan `/home/proscout/offline_data/` directory every 10 minutes
  - Process JSON files in sorted order
  - Upload files to cloud function
  - Delete files after successful upload
  - Handle corrupted/0-byte files (move to problematic/ or delete)
  - Skip persistently failing files

#### 8. **Upload Worker Threads** (ThreadPoolExecutor)
- **Type**: Worker threads (max 3 concurrent)
- **Purpose**: Execute upload tasks asynchronously
- **Lifecycle**: Managed by `ThreadPoolExecutor(max_workers=3)`
- **Responsibilities**:
  - Upload batched payloads to cloud function
  - Handle retries and error recovery
  - Save to disk if upload fails

### Thread Synchronization

#### Locks Used:
1. **GPS Data Lock** (`gps_manager.py`): `threading.Lock()` - Protects GPS data dictionary
2. **IMU Lock** (`IMU_manager.py`): `threading.Lock()` - Protects I2C bus access and IMU buffer
3. **Flow Meter Lock** (`flow_meter.py`): `threading.Lock()` - Protects flow counter
4. **LED Manager Lock** (`leds_manager.py`): `threading.Lock()` - Protects singleton instances

#### Thread-Safe Patterns:
- **Singleton Pattern**: GPS Manager, IMU Manager, LED Service use singleton pattern with locks
- **Buffer Pattern**: IMU data collected in background thread, consumed by main loop
- **Producer-Consumer**: GPS/IMU threads produce data, Session thread consumes

---

## Sensor Sampling Rates & Data Throughput

### Sensor Sampling Rates

| Sensor | Sampling Rate | Collection Method | Notes |
|--------|--------------|-------------------|-------|
| **GPS** | ~1 Hz (1 NMEA sentence/second) | Continuous background thread | Typical GPS modules send NMEA sentences at 1Hz. Multiple sentence types (RMC, GGA, GSA, GSV, ZDA) received continuously |
| **IMU** | Configurable (default: varies) | Continuous background thread | Rate set by `imu_rate_per_second` config parameter. Typically 1-10 Hz |
| **Flow Meter** | Event-driven (pulses) | Background polling thread | No fixed rate - depends on flow. Each pulse increments counter |
| **Camera** | `sleep_interval / 5` | On-demand in main loop | If `sleep_interval = 60s`, camera captures every 12 seconds |
| **Main Loop** | `1 / sleep_interval` Hz | Session thread | Typical: 1/60 Hz = 0.0167 Hz (once per minute) |

### Data Collection Frequencies

**Main Loop Collection:**
- **GPS Data**: Read once per loop iteration (cached, non-blocking)
- **IMU Data**: Buffer read once per loop iteration (all samples since last read)
- **Flow Meter**: Counter read and reset once per loop iteration
- **Camera**: Captured every `camera_interval` iterations

**Example with `sleep_interval = 60 seconds`:**
- Main loop: 1 iteration per minute
- GPS: ~60 NMEA sentences per minute (cached, latest used)
- IMU: If `imu_rate_per_second = 1`: 60 samples per minute (buffered)
- Camera: 1 image per 5 minutes (every 5 iterations)
- Flow Meter: Variable (depends on flow rate)

### Data Size Estimates

#### Per Data Point (Single Payload Entry)

| Component | Size (bytes) | Notes |
|-----------|--------------|-------|
| **GPS Data** | ~150 bytes | Latitude, longitude, altitude, speed, course, satellites, DOP values, timestamps |
| **IMU Data** | ~500-2000 bytes | Depends on buffer size. Each IMU reading: ~200 bytes (9 axes + heading + metadata) |
| **Flow Meter** | ~10 bytes | Single integer counter value |
| **Camera Image** | ~50-200 KB | Base64 encoded JPEG (varies by resolution/compression) |
| **Metadata** | ~100 bytes | Timestamp, device UUID, session timestamp, flags |

**Typical Payload Entry (without image):**
- GPS: 150 bytes
- IMU (10 samples): ~2000 bytes
- Flow Meter: 10 bytes
- Metadata: 100 bytes
- **Total: ~2,260 bytes per entry**

**Payload Entry (with image):**
- Base payload: 2,260 bytes
- Image: ~100 KB (average)
- **Total: ~102,260 bytes per entry**

#### Batch Payload Structure

```json
{
  "device_uuid": "35f6b649-df4f-423c-9e71-7e20fb970670",  // ~36 bytes
  "sessionTimestamp": "2026-01-21T09:52:29.595686",      // ~26 bytes
  "sleep_time": 60,                                        // ~10 bytes
  "payload": [                                             // Array of data points
    {
      "timestamp": "...",
      "flow_meter_counter": 0,
      "latitude": -0.74907,
      "longitude": 36.20410,
      "speed_kmh": 3.765,
      "heading": 123.14,
      "IMU": [...],                                        // Array of IMU readings
      "image_base_64": null,                              // or base64 string
      "gps_fix": true
    },
    // ... more entries
  ]
}
```

### Throughput Calculations

#### Assumptions:
- `sleep_interval = 60 seconds` (1 minute)
- `batch_size = 10` (10 data points per batch)
- `imu_rate_per_second = 1` (1 IMU sample per second)
- Camera: 1 image per 5 minutes (every 5th data point)

#### Per Minute:
- **Data Points Collected**: 1
- **IMU Samples**: 60 (buffered, all included in single data point)
- **GPS Updates**: ~60 NMEA sentences (latest cached)
- **Flow Meter Reads**: 1 (counter reset)

#### Per Batch (10 data points = 10 minutes):
- **Without Images**: 
  - Size: 10 × 2,260 bytes = 22,600 bytes (~22 KB)
  - Compressed (gzip): ~8-12 KB (60-70% compression)
  
- **With Images** (2 images per batch):
  - Base payload: 8 × 2,260 bytes = 18,080 bytes
  - Images: 2 × 100 KB = 200,000 bytes
  - Total: 218,080 bytes (~213 KB)
  - Compressed (gzip): ~150-180 KB (20-30% compression for images)

#### Per Hour:
- **Batches**: 6 batches (60 minutes / 10 minutes per batch)
- **Data Points**: 60
- **Without Images**: 
  - Raw: 60 × 2,260 bytes = 135,600 bytes (~132 KB)
  - Compressed: ~50-80 KB
  - Uploads: 6 batches × 12 KB = ~72 KB
  
- **With Images**:
  - Raw: ~1.3 MB (60 data points + 12 images)
  - Compressed: ~900 KB - 1.1 MB
  - Uploads: 6 batches × 150 KB = ~900 KB

#### Per Day:
- **Without Images**:
  - Raw: ~3.2 MB
  - Compressed: ~1.2-1.9 MB
  - Uploads: ~1.7 MB
  
- **With Images**:
  - Raw: ~31 MB
  - Compressed: ~22-26 MB
  - Uploads: ~22 MB

### Network Bandwidth Requirements

**Average Upload Rate:**
- **Without Images**: ~20 bytes/second (1.2 MB / 24 hours)
- **With Images**: ~250 bytes/second (22 MB / 24 hours)

**Peak Upload Rate** (during batch upload):
- **Without Images**: ~12 KB per batch, every 10 minutes = ~20 bytes/second average, ~2 KB/second peak
- **With Images**: ~150 KB per batch, every 10 minutes = ~250 bytes/second average, ~25 KB/second peak

**Note**: Actual bandwidth depends on:
- Compression ratio (varies with data)
- Image size (varies with scene complexity)
- Network latency and retries
- Offline storage retry uploads

### Storage Requirements (Offline Data)

**Offline Storage Directory**: `/home/proscout/offline_data/`

**Per Offline File** (single batch):
- **Without Images**: ~8-12 KB (compressed)
- **With Images**: ~150-180 KB (compressed)

**Storage Growth Rate** (if offline):
- **Without Images**: ~12 KB per 10 minutes = ~1.7 MB per day
- **With Images**: ~150 KB per 10 minutes = ~22 MB per day

**Recommendation**: Monitor offline storage directory size. With 1 GB available:
- Without images: ~580 days offline capacity
- With images: ~45 days offline capacity

## Component Details

### 1. Main Entry Point (`main.py`)

**Initialization Sequence:**
```
1. Initialize LED Manager Service
2. Set system state to ON
3. Create and start DockingManager
4. Create Session instance
5. Call Session.start()
6. Main thread sleeps (keeps process alive)
```

**Shutdown Sequence:**
```
1. Catch KeyboardInterrupt or Exception
2. Call Session.end()
3. Set LED state to MALFUNCTIONING
4. Exit
```

### 2. Session Class (`session.py`)

**Key Methods:**
- `__init__()`: Initialize components (Camera, IMU, GPS, Upload client)
- `start()`: Start session thread, initialize sensors
- `run()`: Main data collection loop
- `end()`: Stop session, cleanup resources
- `check_gps_health()`: Monitor GPS health, restart if needed
- `check_imu_health()`: Monitor IMU health, restart if needed
- `add_payload_to_batch()`: Add data point to batch
- `flash_batch()`: Submit batch for upload via ThreadPoolExecutor

**Main Loop Flow:**
```
1. Check WiFi download-only mode
2. Get GPS data (cached, non-blocking)
3. Check GPS health (every 10 iterations)
4. Get flow meter counter (reset after read)
5. Get IMU data buffer (reset after read)
6. Check IMU health (every 10 iterations)
7. Capture camera image (every camera_interval iterations)
8. Determine timestamp source (GPS or SYSTEM)
9. Add payload to batch
10. If batch_size reached, trigger upload
11. Sleep for sleep_interval
12. Repeat
```

### 3. GPS Manager (`gps_manager.py`)

**Architecture:**
- **Singleton Pattern**: Global `gps_manager` instance
- **Lazy Initialization**: Created on first `get_gps_manager()` call
- **Background Reader**: Continuous NMEA parsing in daemon thread
- **Thread-Safe Access**: All data access protected by `data_lock`

**Key Methods:**
- `__init__()`: Open serial port, start reader thread
- `_continuous_read()`: Background thread reading NMEA sentences
- `_parse_nmea_line()`: Parse and update GPS data
- `get_gps_data()`: Return cached GPS data (non-blocking)
- `get_data_age()`: Calculate seconds since last NMEA sentence
- `is_healthy()`: Check thread alive and serial connected
- `close()`: Stop thread, close serial port

**NMEA Sentences Parsed:**
- `RMC`: Recommended Minimum (position, speed, course, date/time)
- `GGA`: Global Positioning System Fix Data (position, altitude, satellites)
- `GSA`: GPS DOP and Active Satellites (satellite selection, DOP values)
- `GSV`: GPS Satellites in View (satellite information)
- `ZDA`: Time and Date (more reliable time/date than RMC)

**Restart Conditions:**
- Thread is dead
- Serial port is disconnected
- Data age is None (not initialized)

### 4. IMU Manager (`IMU_manager.py`)

**Architecture:**
- **Background Thread**: Continuously reads I2C sensors
- **Buffer Pattern**: Data collected in `imu_buffer`, consumed by main loop
- **Thread-Safe**: I2C access protected by global `lock`

**Key Methods:**
- `__init__()`: Initialize sensors, load calibration, start update thread
- `update_imu()`: Background thread reading all sensors
- `get_imu_buffer_and_reset()`: Return buffer and clear it (thread-safe)
- `readACCx/y/z()`, `readGYRx/y/z()`, `readMAGx/y/z()`: I2C sensor reads
- `update_tilt_compensated_heading()`: Calculate heading with tilt compensation

**Sensors:**
- **LSM6DSL** (0x6A): Accelerometer + Gyroscope
- **MMC5983MA** (0x30): Magnetometer

**Error Handling:**
- Rate-limited error logging (max once per 10 seconds per sensor/axis)
- Error counting and type breakdown
- Automatic restart on persistent failures

### 5. Flow Meter (`flow_meter.py`)

**Architecture:**
- **GPIO Polling**: Background thread monitors GPIO pin 5
- **Global Counter**: Thread-safe counter incremented on pulses
- **Reset on Read**: Counter reset after each read

**Key Functions:**
- `setup_flow_meter()`: Initialize GPIO, start polling thread
- `polling_monitor()`: Background thread monitoring pin state
- `get_counter_and_reset()`: Return counter value and reset (thread-safe)
- `cleanup()`: Cleanup GPIO resources

### 6. Cloud Function Client (`upload.py`)

**Architecture:**
- **Session Management**: HTTP session with connection pooling
- **Offline Storage**: Saves failed uploads to disk
- **Background Upload**: Daemon thread processes offline files

**Key Methods:**
- `__init__()`: Setup HTTP session, start offline upload thread
- `upload_json()`: Upload batch payload with retry logic
- `save_to_disk()`: Save payload to offline directory
- `upload_offline_data()`: Background thread processing offline files

**Upload Flow:**
```
1. Compress JSON with gzip
2. POST to cloud function endpoint
3. If success (201): Return success
4. If failure: Retry (max 2 retries with exponential backoff)
5. If all retries fail: Save to disk
6. Offline thread will retry later
```

**Offline Upload Flow:**
```
1. Scan offline_data directory
2. Process files in sorted order
3. Check for 0-byte files (delete)
4. Check for JSON errors (move to problematic/)
5. Upload file
6. Delete on success, skip on persistent failure
7. Sleep 10 minutes, repeat
```

### 7. Docking Manager (`docking.py`)

**Architecture:**
- **GPIO Monitoring**: Background thread monitors pin 13
- **State Machine**: HIGH = DOCKED, LOW = UNDOCKED

**Key Methods:**
- `__init__()`: Initialize GPIO pins (TX=6 output, RX=13 input)
- `run()`: Start monitoring thread
- `_monitor_rx_pin()`: Background thread waiting for state changes
- `stop()`: Stop monitoring thread

### 8. LED Manager Service (`leds_manager.py`)

**Architecture:**
- **Singleton Pattern**: Single instance shared across components
- **State Management**: Tracks system, docking, GPS, cellular, IMU, battery states
- **Priority Logic**: Determines LED color/pattern based on state priority

**State Priority (highest to lowest):**
1. BOOTING → Red blink (1000ms)
2. MALFUNCTIONING → Red solid
3. IMU ERROR → Red solid
4. UNDOCKED → Red solid
5. GPS NO_FIX → Red blink (100ms)
6. IMU CALIBRATING → Green blink (100ms)
7. CELLULAR NO_SIGNAL → Green blink (1000ms)
8. ON (all OK) → Green solid
9. Battery charging → Blue (solid if 100%, blink if <100%)

**Communication:**
- Uses Unix socket (`/tmp/led.sock`) to communicate with LED service
- LED service runs as separate systemd service (`leds-service`)

---

## Data Flow

### Data Collection Flow

```
┌─────────────┐
│ Session.run()│
│  (main loop)│
└──────┬──────┘
       │
       ├─→ Get GPS Data (cached, non-blocking)
       │   └─→ GPSManager.get_gps_data()
       │       └─→ Returns cached data from reader thread
       │
       ├─→ Get Flow Counter (reset after read)
       │   └─→ get_counter_and_reset()
       │       └─→ Returns global counter, resets to 0
       │
       ├─→ Get IMU Buffer (reset after read)
       │   └─→ IMUManager.get_imu_buffer_and_reset()
       │       └─→ Returns buffer copy, clears buffer
       │
       ├─→ Capture Camera Image (if enabled)
       │   └─→ Camera.snap_as_base64()
       │
       └─→ Add to Batch
           └─→ add_payload_to_batch()
               └─→ Append to batch_payload list
                   └─→ If batch_size reached:
                       └─→ flash_batch()
                           └─→ ThreadPoolExecutor.submit(upload_json)
```

### Upload Flow

```
┌─────────────────┐
│ flash_batch()   │
└────────┬────────┘
         │
         └─→ ThreadPoolExecutor.submit(upload_json, batch)
             │
             └─→ CloudFunctionClient.upload_json()
                 │
                 ├─→ Compress JSON with gzip
                 │
                 ├─→ POST to cloud function
                 │   ├─→ Success (201): Return
                 │   └─→ Failure: Retry (max 2 retries)
                 │       ├─→ Success: Return
                 │       └─→ All retries failed:
                 │           └─→ save_to_disk()
                 │               └─→ Write to /home/proscout/offline_data/
```

### Offline Upload Flow

```
┌──────────────────────┐
│ upload_offline_data()│
│   (daemon thread)    │
└──────────┬───────────┘
           │
           └─→ While True:
               │
               ├─→ Scan offline_data directory
               │
               ├─→ For each file (sorted):
               │   ├─→ Check if 0 bytes → Delete
               │   ├─→ Try to load JSON
               │   │   └─→ JSON error → Move to problematic/
               │   ├─→ Upload file
               │   │   ├─→ Success → Delete file
               │   │   └─→ Failure → Skip (continue to next)
               │   └─→ Sleep 1 second between files
               │
               └─→ Sleep 10 minutes
                   └─→ Repeat
```

---

## Error Handling & Recovery

### GPS Health Monitoring

**Check Frequency**: Every 10 iterations of main loop

**Health Checks:**
1. **Thread Alive**: Check if reader thread is running
2. **Serial Connected**: Check if serial port is open
3. **Data Age**: Check if data age is None (not initialized)

**Recovery:**
- **Restart GPS Manager**: Close and reopen serial port
- **Max Restarts**: 5 attempts before giving up
- **Reset on Success**: Reset restart counter when GPS recovers

### IMU Health Monitoring

**Check Frequency**: Every 10 iterations of main loop

**Health Checks:**
1. **Data Timeout**: Check if no IMU data received for 30 seconds
2. **Thread Alive**: Check if update thread is running

**Recovery:**
- **Restart IMU Manager**: Stop thread, recreate manager
- **Max Restarts**: 5 attempts before giving up
- **Reset on Success**: Reset restart counter when IMU recovers

**Error Rate Limiting:**
- I2C errors logged max once per 10 seconds per sensor/axis
- Error counting and type breakdown in log messages

### Upload Error Handling

**Retry Logic:**
- Max 2 retries with exponential backoff (1s, 2s, 4s)
- Connection errors trigger session recreation
- Timeout errors retry with backoff
- All failures save to disk for offline upload

**Offline File Handling:**
- 0-byte files: Deleted immediately
- JSON errors: Moved to `problematic/` directory
- Persistent failures: Skipped after max failures
- Successful uploads: Deleted from disk

### Network Connectivity

**Cellular State:**
- Monitored via network interface status
- LED indicates NO_SIGNAL state
- Uploads fail gracefully, save to disk

**WiFi Download-Only Mode:**
- If enabled and WiFi connected: Skip data collection
- Used for maintenance/debugging

---

## Configuration

### Configuration File (`config.ini`)

**Sections:**
- `[Setup]`: Main configuration parameters

**Key Parameters:**
- `sleep_interval`: Seconds between data collection cycles
- `batch_size`: Number of data points before upload
- `imu_rate_per_second`: IMU sampling rate
- `camera`: Enable/disable camera
- `flow_meter`: Enable/disable flow meter
- `imu`: Enable/disable IMU
- `production`: Use production or staging cloud function URL
- `wifi_download_only`: Skip data collection when WiFi connected

### Device ID

**Location**: `/home/proscout/ProScout-master/device-manager/device_id.txt`
**Content**: Device UUID (one line)
**Usage**: Included in all uploads as `device_uuid`

---

## Calling Routines

### Initialization Sequence

```python
# main.py
main()
  ├─→ LedsManagerService()  # Singleton
  ├─→ set_system_state(ON)
  ├─→ DockingManager()
  │   └─→ run()  # Starts monitor thread
  └─→ Session()
      └─→ start()
          ├─→ CloudFunctionClient()  # Starts offline upload thread
          ├─→ IMUManager()  # Starts IMU update thread
          ├─→ GPSManager (lazy init on first use)  # Starts GPS reader thread
          ├─→ Camera() (if enabled)
          ├─→ setup_flow_meter()  # Starts flow meter polling thread
          └─→ Thread(target=run).start()  # Starts session thread
```

### Main Loop Sequence (Session.run())

```python
while running:
  ├─→ Check WiFi download-only mode
  ├─→ get_gps_data()  # Non-blocking, cached
  ├─→ Check GPS health (every 10 iterations)
  ├─→ get_counter_and_reset()  # Flow meter
  ├─→ get_imu_buffer_and_reset()  # IMU data
  ├─→ Check IMU health (every 10 iterations)
  ├─→ Camera.snap_as_base64()  # If camera_interval reached
  ├─→ Determine timestamp (GPS or SYSTEM)
  ├─→ add_payload_to_batch()
  ├─→ flash_batch()  # If batch_size reached
  │   └─→ ThreadPoolExecutor.submit(upload_json)
  └─→ sleep(sleep_interval)
```

### Upload Routine

```python
upload_json(batch_payload)
  ├─→ Create JSON payload
  ├─→ Compress with gzip
  ├─→ POST to cloud function
  │   ├─→ Success (201): Return
  │   └─→ Failure: Retry (max 2)
  │       ├─→ Success: Return
  │       └─→ All failed: save_to_disk()
  └─→ Return result
```

### Health Check Routines

```python
check_gps_health()
  ├─→ is_gps_healthy()?
  │   └─→ No: restart_gps()
  ├─→ get_gps_data_age() is None?
  │   └─→ Yes: restart_gps()
  └─→ Return True

check_imu_health()
  ├─→ Time since last data > timeout?
  │   └─→ Yes: restart_imu()
  └─→ Return True
```

---

## Thread Lifecycle Summary

| Thread | Type | Started By | Stopped By | Purpose |
|--------|------|------------|------------|---------|
| Main | Main | OS | OS | Application entry point |
| Docking Monitor | Daemon | DockingManager.run() | monitor_active=False | Monitor GPIO pin 13 |
| Session | Non-daemon | Session.start() | running=False | Main data collection |
| GPS Reader | Daemon | GPSManager.__init__() | running=False | Read NMEA sentences |
| IMU Update | Daemon | IMUManager.__init__() | Thread stops | Read I2C sensors |
| Flow Meter Polling | Daemon | setup_flow_meter() | Process exit | Monitor GPIO pin 5 |
| Offline Upload | Daemon | CloudFunctionClient.__init__() | Process exit | Upload offline files |
| Upload Workers | Worker | ThreadPoolExecutor | Task complete | Execute uploads |

---

## Key Design Patterns

1. **Singleton Pattern**: GPS Manager, IMU Manager, LED Service
2. **Producer-Consumer**: GPS/IMU threads produce, Session consumes
3. **Buffer Pattern**: IMU data buffered, consumed in batches
4. **Retry Pattern**: Upload retries with exponential backoff
5. **Offline-First**: Failed uploads saved to disk, retried later
6. **Health Monitoring**: Periodic health checks with automatic recovery
7. **State Machine**: LED service uses priority-based state machine

---

## Performance Considerations

- **Non-blocking Reads**: GPS data cached, no blocking I/O in main loop
- **Thread Pool**: Uploads executed asynchronously (max 3 concurrent)
- **Batch Processing**: Data collected in batches before upload
- **Connection Pooling**: HTTP session reused for uploads
- **Rate Limiting**: Error logging rate-limited to prevent log spam
- **Memory Management**: IMU buffer cleared after read, batches cleared after upload

---

## Security Considerations

- **Device UUID**: Unique identifier for each device
- **HTTPS**: All cloud communications use HTTPS
- **Connection Close**: Connections closed after each request
- **Offline Storage**: Sensitive data stored locally when offline

---

## Future Enhancements

- **Configurable Health Check Intervals**: Make health check frequencies configurable
- **Metrics Collection**: Add performance metrics collection
- **Remote Configuration**: Support remote configuration updates
- **OTA Updates**: Over-the-air firmware updates
- **Enhanced Error Reporting**: More detailed error telemetry

---

## Appendix: Typical Configuration Values

### Default Configuration Example

```ini
[Setup]
sleep_interval = 60              # Seconds between data collection cycles
batch_size = 10                 # Data points per batch before upload
imu_rate_per_second = 1         # IMU sampling rate (Hz)
camera = True                   # Enable camera
flow_meter = True               # Enable flow meter
imu = True                      # Enable IMU
production = True                # Use production cloud function
wifi_download_only = False      # Skip data collection when WiFi connected
```

### Resulting Frequencies

With above configuration:
- **Main Loop**: 1 iteration per minute
- **GPS**: ~1 Hz (60 NMEA sentences/minute, latest cached)
- **IMU**: 1 Hz (60 samples/minute, buffered)
- **Camera**: 1 image per 5 minutes
- **Flow Meter**: Event-driven (variable)
- **Batch Upload**: Every 10 minutes
- **Health Checks**: GPS every 10 iterations, IMU every 10 iterations

---

*Document Version: 1.1*  
*Last Updated: 2026-01-21*  
*Added: Sensor sampling rates and throughput estimates*

