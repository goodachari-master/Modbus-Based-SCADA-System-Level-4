import threading
import time
import json
import os
from datetime import datetime
import logging
from collections import deque
from database import DatabaseHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DeviceManager:
    """Manages multiple ESP32 devices with MySQL persistence"""
    
    def __init__(self, db_config=None):
        self.devices = {}  # {device_id: device_info} - in-memory cache
        self.active_device = None
        self.lock = threading.Lock()
        
        # Initialize database
        if db_config is None:
            db_config = {
                'host': 'localhost',
                'user': 'root',
                'password': 'Veejnas@4002',  # Change this to your MySQL password
                'database': 'scada_db'
            }
        
        self.db = DatabaseHandler(**db_config)
        self.load_devices_from_db()
        
    def load_devices_from_db(self):
        """Load devices from database into memory"""
        try:
            db_devices = self.db.get_devices()
            for device in db_devices:
                device_id = device['device_id']
                self.devices[device_id] = {
                    'id': device_id,
                    'name': device.get('name', device_id),
                    'room': device.get('room', 'Unknown'),
                    'ip': device.get('ip'),
                    'port': device.get('port', 502),
                    'connected': device.get('connected', False),
                    'last_seen': device.get('last_seen'),
                    'modbus_client': None,
                    'control_logic': None,
                    'temperature': None,
                    'humidity': None,
                    'temp_led_state': False,
                    'humidity_led_state': False,
                    'buzzer_state': False,
                    'manual_temp_led': None,
                    'manual_humidity_led': None,
                    'manual_buzzer': None,
                    'temp_threshold': float(device.get('temp_threshold', 30.0)),
                    'humidity_threshold': float(device.get('humidity_threshold', 70.0)),
                    'buzzer_temp_threshold': float(device.get('buzzer_temp_threshold', 35.0)),
                    'buzzer_humidity_threshold': float(device.get('buzzer_humidity_threshold', 80.0)),
                    'data_buffer': deque(maxlen=10),
                    'events': deque(maxlen=50)
                }
            logger.info(f"Loaded {len(self.devices)} devices from database")
        except Exception as e:
            logger.error(f"Error loading devices from DB: {e}")
    
    def add_device(self, device_id, ip, port=502, room=None, name=None):
        """Add a new device"""
        with self.lock:
            if device_id not in self.devices:
                room_name = room or device_id
                device_name = name or room_name
                
                # Add to database
                success = self.db.add_device(device_id, device_name, room_name, ip, port)
                
                if success:
                    self.devices[device_id] = {
                        'id': device_id,
                        'name': device_name,
                        'room': room_name,
                        'ip': ip,
                        'port': port,
                        'connected': False,
                        'last_seen': None,
                        'modbus_client': None,
                        'control_logic': None,
                        'temperature': None,
                        'humidity': None,
                        'temp_led_state': False,
                        'humidity_led_state': False,
                        'buzzer_state': False,
                        'manual_temp_led': None,
                        'manual_humidity_led': None,
                        'manual_buzzer': None,
                        'temp_threshold': 30.0,
                        'humidity_threshold': 70.0,
                        'buzzer_temp_threshold': 35.0,
                        'buzzer_humidity_threshold': 80.0,
                        'data_buffer': deque(maxlen=10),
                        'events': deque(maxlen=50)
                    }
                    logger.info(f"Added device: {device_id} at {ip}:{port}")
                    return True
            return False
    
    def remove_device(self, device_id):
        """Remove a device"""
        with self.lock:
            if device_id in self.devices:
                # Disconnect if connected
                if self.devices[device_id].get('modbus_client'):
                    try:
                        self.devices[device_id]['modbus_client'].disconnect()
                    except:
                        pass
                
                # Remove from database
                self.db.remove_device(device_id)
                
                del self.devices[device_id]
                if self.active_device == device_id:
                    self.active_device = None
                
                logger.info(f"Removed device: {device_id}")
                return True
            return False
    
    def get_device(self, device_id):
        """Get device info"""
        return self.devices.get(device_id)
    
    def get_all_devices(self):
        """Get all devices"""
        return self.devices
    
    def get_device_list(self, include_disconnected=True):
        """Get list of devices for frontend
        
        Args:
            include_disconnected: If True, returns all devices. If False, only connected devices.
        """
        devices_list = []
        for device_id, device in self.devices.items():
            # Filter out disconnected devices if requested
            if not include_disconnected and not device.get('connected', False):
                continue
                
            devices_list.append({
                'id': device_id,
                'name': device.get('name', device_id),
                'room': device.get('room', 'Unknown'),
                'ip': device.get('ip'),
                'port': device.get('port', 502),
                'connected': device.get('connected', False),
                'last_seen': device.get('last_seen'),
                'temperature': device.get('temperature'),
                'humidity': device.get('humidity'),
                'temp_led_state': device.get('temp_led_state', False),
                'humidity_led_state': device.get('humidity_led_state', False),
                'buzzer_state': device.get('buzzer_state', False),
                'manual_temp_led': device.get('manual_temp_led'),
                'manual_humidity_led': device.get('manual_humidity_led'),
                'manual_buzzer': device.get('manual_buzzer')
            })
        return devices_list
    
    def set_active_device(self, device_id):
        """Set the active device for control"""
        if device_id in self.devices:
            self.active_device = device_id
            logger.info(f"Active device set to: {device_id}")
            return True
        return False
    
    def get_active_device(self):
        """Get the active device ID"""
        return self.active_device
    
    def update_device_data(self, device_id, data):
        """Update device data"""
        if device_id in self.devices:
            with self.lock:
                self.devices[device_id].update(data)
                self.devices[device_id]['last_seen'] = datetime.now().isoformat()
                
                # Update connection status in database
                if 'connected' in data:
                    self.db.update_device_status(device_id, data['connected'])
                
                # Update thresholds in database if changed
                thresholds_changed = any(key in data for key in [
                    'temp_threshold', 'humidity_threshold', 
                    'buzzer_temp_threshold', 'buzzer_humidity_threshold'
                ])
                if thresholds_changed:
                    self.db.update_device_thresholds(device_id, {
                        'temp_threshold': self.devices[device_id].get('temp_threshold', 30.0),
                        'humidity_threshold': self.devices[device_id].get('humidity_threshold', 70.0),
                        'buzzer_temp_threshold': self.devices[device_id].get('buzzer_temp_threshold', 35.0),
                        'buzzer_humidity_threshold': self.devices[device_id].get('buzzer_humidity_threshold', 80.0)
                    })
    
    def add_sensor_reading(self, device_id, temperature, humidity):
        """Add sensor reading to database and memory buffer"""
        if device_id in self.devices:
            # Add to database (maintains last 10 records)
            self.db.add_sensor_reading(device_id, temperature, humidity)
            
            # Also keep in memory buffer
            self.devices[device_id]['data_buffer'].append({
                'temperature': temperature,
                'humidity': humidity,
                'timestamp': datetime.now().isoformat()
            })
            
            # Update current values
            self.devices[device_id]['temperature'] = temperature
            self.devices[device_id]['humidity'] = humidity
    
    def get_sensor_history(self, device_id, limit=10):
        """Get sensor history from database"""
        return self.db.get_sensor_history(device_id, limit)
    
    def add_device_event(self, device_id, event_type, description):
        """Add event for specific device to database and memory"""
        if device_id in self.devices:
            # Add to database
            self.db.add_event(device_id, event_type, description)
            
            # Also keep in memory buffer
            event = {
                'timestamp': datetime.now().isoformat(),
                'type': event_type,
                'description': description,
                'device_id': device_id,
                'device_name': self.devices[device_id].get('name', device_id)
            }
            self.devices[device_id]['events'].append(event)
            return event
        return None
    
    def get_device_events(self, device_id, limit=50):
        """Get events for specific device from database"""
        return self.db.get_events(device_id, limit)
    
    def get_all_events(self, limit=100):
        """Get events from all devices from database"""
        return self.db.get_events(limit=limit)
    
    def close(self):
        """Close database connection"""
        self.db.close()