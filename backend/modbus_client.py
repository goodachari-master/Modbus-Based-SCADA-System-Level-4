import time
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException, ConnectionException
import logging
from datetime import datetime
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ModbusClient:
    def __init__(self):
        self.host = None
        self.port = None
        self.client = None
        self.connected = False
        self.connection_lock = threading.Lock()
        self.last_successful_read = None
        self.connection_attempts = 0
        self.max_connection_attempts = 3
        self.device_info = {}
        
    def connect(self, host, port=502):
        """Establish connection to Modbus server"""
        with self.connection_lock:
            try:
                # Close existing connection if any
                if self.client:
                    self.client.close()
                
                self.host = host
                self.port = port
                
                logger.info(f"Attempting to connect to ESP32 at {host}:{port}")
                
                # Create new client with timeout
                self.client = ModbusTcpClient(host, port=port, timeout=5)
                self.connected = self.client.connect()
                
                if self.connected:
                    logger.info(f"✅ Successfully connected to ESP32 at {host}:{port}")
                    self.connection_attempts = 0
                    self.last_successful_read = datetime.now()
                    
                    # Try to read device info (optional)
                    self._read_device_info()
                    
                    return True, "Connected successfully"
                else:
                    logger.error(f"❌ Failed to connect to ESP32 at {host}:{port}")
                    self.client = None
                    return False, "Connection failed - ESP32 not responding"
                    
            except Exception as e:
                logger.error(f"Connection error: {e}")
                self.connected = False
                self.client = None
                return False, f"Connection error: {str(e)}"
    
    def disconnect(self):
        """Disconnect from Modbus server"""
        with self.connection_lock:
            if self.client:
                try:
                    self.client.close()
                    logger.info(f"Disconnected from ESP32 at {self.host}:{self.port}")
                except:
                    pass
                finally:
                    self.client = None
                    self.connected = False
                    self.host = None
                    self.port = None
                    return True
            return False
    
    def _read_device_info(self):
        """Read device information if available"""
        self.device_info = {
            'host': self.host,
            'port': self.port,
            'connected_since': self.last_successful_read.isoformat() if self.last_successful_read else None
        }
    
    def read_temperature(self):
        """Read temperature from input register 0"""
        if not self._ensure_connected():
            return None
            
        try:
            result = self.client.read_input_registers(0, 1)
            
            if result and hasattr(result, 'registers') and len(result.registers) > 0:
                raw_value = result.registers[0]
                
                if raw_value == -999:  # Error value from ESP32
                    logger.warning("ESP32 reported temperature sensor error")
                    return None
                
                temperature = raw_value / 10.0
                self.last_successful_read = datetime.now()
                return temperature
            else:
                logger.warning("Invalid temperature response from ESP32")
                return None
                
        except (ModbusException, ConnectionException) as e:
            logger.error(f"Modbus error reading temperature: {e}")
            self.connected = False
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading temperature: {e}")
            return None
    
    def read_humidity(self):
        """Read humidity from input register 1"""
        if not self._ensure_connected():
            return None
            
        try:
            result = self.client.read_input_registers(1, 1)
            
            if result and hasattr(result, 'registers') and len(result.registers) > 0:
                raw_value = result.registers[0]
                
                if raw_value == -999:  # Error value from ESP32
                    logger.warning("ESP32 reported humidity sensor error")
                    return None
                
                humidity = raw_value / 10.0
                self.last_successful_read = datetime.now()
                return humidity
            else:
                logger.warning("Invalid humidity response from ESP32")
                return None
                
        except (ModbusException, ConnectionException) as e:
            logger.error(f"Modbus error reading humidity: {e}")
            self.connected = False
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading humidity: {e}")
            return None
    
    def read_all_sensors(self):
        """Read both temperature and humidity in one call"""
        if not self._ensure_connected():
            return None, None
            
        try:
            # Read 2 registers starting from 0
            result = self.client.read_input_registers(0, 2)
            
            if result and hasattr(result, 'registers') and len(result.registers) >= 2:
                temp_raw = result.registers[0]
                hum_raw = result.registers[1]
                
                temperature = None if temp_raw == -999 else temp_raw / 10.0
                humidity = None if hum_raw == -999 else hum_raw / 10.0
                
                self.last_successful_read = datetime.now()
                return temperature, humidity
            else:
                logger.warning("Invalid sensor data from ESP32")
                return None, None
                
        except (ModbusException, ConnectionException) as e:
            logger.error(f"Modbus error reading sensors: {e}")
            self.connected = False
            return None, None
        except Exception as e:
            logger.error(f"Unexpected error reading sensors: {e}")
            return None, None
    
    def set_temp_led(self, state):
        """Set temperature LED state (True=ON, False=OFF)"""
        return self._write_coil(0, state, "Temperature LED")
    
    def set_humidity_led(self, state):
        """Set humidity LED state (True=ON, False=OFF)"""
        return self._write_coil(1, state, "Humidity LED")
    
    def set_buzzer(self, state):
        """Set common buzzer state (True=ON, False=OFF)"""
        return self._write_coil(2, state, "Buzzer")
    
    def _write_coil(self, coil_address, state, device_name):
        """Internal method to write to coils"""
        if not self._ensure_connected():
            return False
            
        try:
            self.client.write_coil(coil_address, state)
            logger.info(f"{device_name} set to {'ON' if state else 'OFF'}")
            return True
        except (ModbusException, ConnectionException) as e:
            logger.error(f"Error setting {device_name}: {e}")
            self.connected = False
            return False
        except Exception as e:
            logger.error(f"Unexpected error setting {device_name}: {e}")
            return False
    
    def _ensure_connected(self):
        """Ensure connection is active before operations"""
        if not self.connected or not self.client:
            return False
        return True
    
    def test_connection(self):
        """Test if connection is still alive"""
        if not self.connected or not self.client:
            return False
        
        try:
            # Try to read a single register to test connection
            result = self.client.read_input_registers(0, 1)
            if result and hasattr(result, 'registers'):
                return True
            else:
                self.connected = False
                return False
        except:
            self.connected = False
            return False
    
    def get_connection_status(self):
        """Get detailed connection status"""
        return {
            'connected': self.connected,
            'host': self.host,
            'port': self.port,
            'last_read': self.last_successful_read.isoformat() if self.last_successful_read else None,
            'device_info': self.device_info
        }