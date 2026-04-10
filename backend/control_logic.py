import time
import threading
from datetime import datetime
from collections import deque
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CircularBuffer:
    """Fixed-size circular buffer for sensor data"""
    def __init__(self, max_size=10):
        self.buffer = deque(maxlen=max_size)
        self.max_size = max_size
    
    def add(self, temperature, humidity):
        """Add sensor readings to buffer"""
        timestamp = datetime.now().isoformat()
        self.buffer.append({
            'timestamp': timestamp,
            'temperature': round(temperature, 1) if temperature else None,
            'humidity': round(humidity, 1) if humidity else None
        })
        logger.info(f"Buffer: added T={temperature}°C, H={humidity}% (size: {len(self.buffer)})")
    
    def get_all(self):
        """Get all readings in chronological order"""
        return list(self.buffer)
    
    def get_latest(self):
        """Get most recent reading"""
        if self.buffer:
            return self.buffer[-1]
        return None
    
    def clear(self):
        """Clear buffer"""
        self.buffer.clear()
        logger.info("Buffer cleared")

class ControlLogic:
    def __init__(self, modbus_client):
        self.modbus = modbus_client
        self.running = False
        self.thread = None
        self.connection_monitor_thread = None
        
        # Circular buffer for sensor data (max 10 entries)
        self.data_buffer = CircularBuffer(max_size=10)
        
        # Default thresholds
        self.temp_threshold = 30.0  # °C
        self.humidity_threshold = 70.0  # %
        self.buzzer_temp_threshold = 35.0  # °C (critical temperature for buzzer)
        self.buzzer_humidity_threshold = 80.0  # % (critical humidity for buzzer)
        
        # Current states
        self.current_temp = None
        self.current_humidity = None
        self.temp_led_state = False
        self.humidity_led_state = False
        self.buzzer_state = False
        self.last_update = None
        
        # Manual override flags - None = auto, True = forced ON, False = forced OFF
        self.manual_temp_led = None
        self.manual_humidity_led = None
        self.manual_buzzer = None
        
        # Events log (keep last 50 events)
        self.events = deque(maxlen=50)
        
        # System status
        self.system_status = {
            'esp32': 'disconnected',
            'backend': 'running',
            'last_heartbeat': datetime.now().isoformat()
        }
        
        self.add_event('SYSTEM', 'Control logic initialized')
    
    def add_event(self, event_type, description):
        """Add event to circular log"""
        self.events.append({
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'description': description
        })
        logger.info(f"EVENT [{event_type}]: {description}")
    
    def set_thresholds(self, temp=None, humidity=None, buzzer_temp=None, buzzer_humidity=None):
        """Set all thresholds"""
        changes = []
        if temp is not None:
            self.temp_threshold = float(temp)
            changes.append(f"Temp LED={temp}°C")
        if humidity is not None:
            self.humidity_threshold = float(humidity)
            changes.append(f"Humidity LED={humidity}%")
        if buzzer_temp is not None:
            self.buzzer_temp_threshold = float(buzzer_temp)
            changes.append(f"Buzzer Temp={buzzer_temp}°C")
        if buzzer_humidity is not None:
            self.buzzer_humidity_threshold = float(buzzer_humidity)
            changes.append(f"Buzzer Humidity={buzzer_humidity}%")
        
        if changes:
            self.add_event('CONFIG', f"Thresholds updated: {', '.join(changes)}")
    
    def set_manual_control(self, device, state):
        """
        Set manual override for devices
        state = True  -> Force ON
        state = False -> Force OFF
        state = None  -> Auto mode
        """
        if device == 'temp_led':
            old_state = self.manual_temp_led
            self.manual_temp_led = state
            
            if state is True:
                self.modbus.set_temp_led(True)
                self.temp_led_state = True
                if old_state != state:
                    self.add_event('MANUAL', "Temp LED forced ON (manual)")
            elif state is False:
                self.modbus.set_temp_led(False)
                self.temp_led_state = False
                if old_state != state:
                    self.add_event('MANUAL', "Temp LED forced OFF (manual)")
            else:  # Auto mode
                if old_state is not None:
                    self.add_event('SYSTEM', "Temp LED returned to auto mode")
                    
        elif device == 'humidity_led':
            old_state = self.manual_humidity_led
            self.manual_humidity_led = state
            
            if state is True:
                self.modbus.set_humidity_led(True)
                self.humidity_led_state = True
                if old_state != state:
                    self.add_event('MANUAL', "Humidity LED forced ON (manual)")
            elif state is False:
                self.modbus.set_humidity_led(False)
                self.humidity_led_state = False
                if old_state != state:
                    self.add_event('MANUAL', "Humidity LED forced OFF (manual)")
            else:  # Auto mode
                if old_state is not None:
                    self.add_event('SYSTEM', "Humidity LED returned to auto mode")
                    
        elif device == 'buzzer':
            old_state = self.manual_buzzer
            self.manual_buzzer = state
            
            if state is True:
                self.modbus.set_buzzer(True)
                self.buzzer_state = True
                if old_state != state:
                    self.add_event('MANUAL', "Buzzer forced ON (manual)")
            elif state is False:
                self.modbus.set_buzzer(False)
                self.buzzer_state = False
                if old_state != state:
                    self.add_event('MANUAL', "Buzzer forced OFF (manual)")
            else:  # Auto mode
                if old_state is not None:
                    self.add_event('SYSTEM', "Buzzer returned to auto mode")
    
    def reset_manual(self, device=None):
        """Reset to automatic control for specific device or all"""
        if device == 'temp_led' or device is None:
            if self.manual_temp_led is not None:
                self.set_manual_control('temp_led', None)
        if device == 'humidity_led' or device is None:
            if self.manual_humidity_led is not None:
                self.set_manual_control('humidity_led', None)
        if device == 'buzzer' or device is None:
            if self.manual_buzzer is not None:
                self.set_manual_control('buzzer', None)
    
    def monitor_connection(self):
        """Monitor connection status"""
        while self.running:
            try:
                if self.modbus.connected:
                    # Test connection periodically
                    if not self.modbus.test_connection():
                        self.system_status['esp32'] = 'disconnected'
                        self.add_event('WARNING', "ESP32 connection lost")
                    else:
                        self.system_status['esp32'] = 'connected'
                else:
                    self.system_status['esp32'] = 'disconnected'
                
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Connection monitor error: {e}")
    
    def control_loop(self):
        """Main control logic loop"""
        logger.info("Control loop started")
        self.add_event('SYSTEM', "Control loop started")
        
        while self.running:
            try:
                # Update ESP32 status
                self.system_status['esp32'] = 'connected' if self.modbus.connected else 'disconnected'
                self.system_status['last_heartbeat'] = datetime.now().isoformat()
                
                # Check if connection is lost
                if not self.modbus.connected:
                    logger.error("❌ Connection lost in control loop. Terminating control loop.")
                    self.add_event('ERROR', "ESP32 connection lost - Monitoring terminated")
                    self.running = False  # Terminate control loop
                    break
                
                # Read both sensors
                temp, humidity = self.modbus.read_all_sensors()
                
                if temp is not None or humidity is not None:
                    self.current_temp = temp
                    self.current_humidity = humidity
                    self.last_update = datetime.now()
                    
                    # Add to circular buffer (automatically handles max size)
                    if temp is not None and humidity is not None:
                        self.data_buffer.add(temp, humidity)
                    
                    # Automatic control logic for Temperature LED (only if not in manual mode)
                    if self.manual_temp_led is None and temp is not None:
                        new_temp_led_state = temp >= self.temp_threshold
                        if new_temp_led_state != self.temp_led_state:
                            self.modbus.set_temp_led(new_temp_led_state)
                            self.temp_led_state = new_temp_led_state
                            self.add_event('AUTO', f"Temp LED {'ON' if new_temp_led_state else 'OFF'} (Temp: {temp}°C)")
                    
                    # Automatic control logic for Humidity LED (only if not in manual mode)
                    if self.manual_humidity_led is None and humidity is not None:
                        new_humidity_led_state = humidity >= self.humidity_threshold
                        if new_humidity_led_state != self.humidity_led_state:
                            self.modbus.set_humidity_led(new_humidity_led_state)
                            self.humidity_led_state = new_humidity_led_state
                            self.add_event('AUTO', f"Humidity LED {'ON' if new_humidity_led_state else 'OFF'} (Humidity: {humidity}%)")
                    
                    # Automatic control logic for Common Buzzer (only if not in manual mode)
                    if self.manual_buzzer is None:
                        # Buzzer triggers if EITHER temperature OR humidity exceeds critical thresholds
                        temp_alarm = temp is not None and temp >= self.buzzer_temp_threshold
                        humidity_alarm = humidity is not None and humidity >= self.buzzer_humidity_threshold
                        new_buzzer_state = temp_alarm or humidity_alarm
                        
                        if new_buzzer_state != self.buzzer_state:
                            self.modbus.set_buzzer(new_buzzer_state)
                            self.buzzer_state = new_buzzer_state
                            
                            if new_buzzer_state:
                                reasons = []
                                if temp_alarm:
                                    reasons.append(f"Temp={temp}°C")
                                if humidity_alarm:
                                    reasons.append(f"Humidity={humidity}%")
                                self.add_event('ALARM', f"Buzzer ON - Critical: {', '.join(reasons)}")
                            else:
                                self.add_event('AUTO', "Buzzer OFF")
                    
                    # Check for individual alarm conditions
                    if temp is not None and temp >= self.buzzer_temp_threshold:
                        self.add_event('WARNING', f"High temperature: {temp}°C")
                    
                    if humidity is not None and humidity >= self.buzzer_humidity_threshold:
                        self.add_event('WARNING', f"High humidity: {humidity}%")
                        
                else:
                    # Sensor read failed
                    if self.modbus.connected:
                        self.add_event('WARNING', "Failed to read sensors from ESP32")
                    else:
                        # Connection lost during sensor reading
                        logger.error("❌ Connection lost during sensor reading. Terminating control loop.")
                        self.add_event('ERROR', "ESP32 connection lost during read - Monitoring terminated")
                        self.running = False
                        break
                
            except Exception as e:
                logger.error(f"Error in control loop: {e}")
                self.add_event('ERROR', f"Control loop error: {str(e)}")
            
            time.sleep(2)  # Loop every 2 seconds
        
        # Ensure connection status reflects termination
        self.system_status['esp32'] = 'disconnected'
        logger.info("Control loop finished")
    
    def start(self):
        """Start the control system"""
        if not self.running:
            self.running = True
            
            # Start control loop thread
            self.thread = threading.Thread(target=self.control_loop)
            self.thread.daemon = True
            self.thread.start()
            
            # Start connection monitor thread
            self.connection_monitor_thread = threading.Thread(target=self.monitor_connection)
            self.connection_monitor_thread.daemon = True
            self.connection_monitor_thread.start()
            
            logger.info("✅ Control system started")
            self.add_event('SYSTEM', "System started")
            return True
        return False
    
    def stop(self):
        """Stop the control system"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        if self.connection_monitor_thread:
            self.connection_monitor_thread.join(timeout=5)
        logger.info("Control system stopped")
        self.add_event('SYSTEM', "System stopped")
    
    def get_status(self):
        """Get complete system status"""
        return {
            # Current readings
            'temperature': self.current_temp,
            'humidity': self.current_humidity,
            'temp_led_state': self.temp_led_state,
            'humidity_led_state': self.humidity_led_state,
            'buzzer_state': self.buzzer_state,
            'last_update': self.last_update.isoformat() if self.last_update else None,
            
            # Configuration
            'temp_threshold': self.temp_threshold,
            'humidity_threshold': self.humidity_threshold,
            'buzzer_temp_threshold': self.buzzer_temp_threshold,
            'buzzer_humidity_threshold': self.buzzer_humidity_threshold,
            
            # Control mode - True=Manual ON, False=Manual OFF, None=Auto
            'manual_temp_led': self.manual_temp_led,
            'manual_humidity_led': self.manual_humidity_led,
            'manual_buzzer': self.manual_buzzer,
            
            # Connection status
            'modbus': self.modbus.get_connection_status(),
            
            # System status
            'system': self.system_status,
            
            # Buffer info
            'buffer_size': len(self.data_buffer.buffer),
            'buffer_max': self.data_buffer.buffer.maxlen
        }
    
    def get_sensor_history(self):
        """Get sensor history from circular buffer"""
        return self.data_buffer.get_all()
    
    def get_events(self):
        """Get recent events"""
        return list(self.events)
    
    def clear_buffer(self):
        """Manually clear sensor buffer"""
        self.data_buffer.clear()
        self.add_event('SYSTEM', "Sensor buffer cleared")
        return True