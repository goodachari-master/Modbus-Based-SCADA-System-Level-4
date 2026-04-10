import mysql.connector
from mysql.connector import Error, pooling
import logging
from datetime import datetime
from collections import deque
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseHandler:
    """MySQL database handler for SCADA system with thread-safe pooling"""
    
    def __init__(self, host='localhost', user='root', password='Veejnas@4002', database='scada_db'):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.db_pool = None
        self.connect()
        self.init_database()
    
    def connect(self):
        """Initialize MySQL connection pool"""
        try:
            # First connect without database to create it if needed
            temp_conn = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                connection_timeout=10
            )
            cursor = temp_conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.database}")
            cursor.close()
            temp_conn.close()
            
            # Create connection pool
            self.db_pool = pooling.MySQLConnectionPool(
                pool_name="scada_pool",
                pool_size=10,
                pool_reset_session=True,
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                connection_timeout=10
            )
            logger.info(f"✅ MySQL connection pool initialized: {self.database}")
            return True
        except Error as e:
            logger.error(f"❌ Database pool initialization error: {e}")
            return False
    
    def get_connection(self):
        """Get a connection from the pool with retry logic"""
        try:
            if not self.db_pool:
                if not self.connect():
                    return None
            
            conn = self.db_pool.get_connection()
            if not conn.is_connected():
                conn.reconnect(attempts=3, delay=1)
            return conn
        except Error as e:
            logger.error(f"❌ Failed to get connection from pool: {e}")
            # Try re-initializing the pool if it fails
            self.connect()
            try:
                return self.db_pool.get_connection() if self.db_pool else None
            except:
                return None
    
    def init_database(self):
        """Initialize database tables"""
        conn = self.get_connection()
        if not conn:
            return
        
        try:
            cursor = conn.cursor()
            
            # Create devices table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    device_id VARCHAR(50) PRIMARY KEY,
                    name VARCHAR(100),
                    room VARCHAR(100),
                    ip VARCHAR(50),
                    port INT DEFAULT 502,
                    connected BOOLEAN DEFAULT FALSE,
                    last_seen DATETIME,
                    temp_threshold FLOAT DEFAULT 30.0,
                    humidity_threshold FLOAT DEFAULT 70.0,
                    buzzer_temp_threshold FLOAT DEFAULT 35.0,
                    buzzer_humidity_threshold FLOAT DEFAULT 80.0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)
            
            # Create events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    device_id VARCHAR(50),
                    event_type VARCHAR(50),
                    description TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE
                )
            """)
            
            conn.commit()
            logger.info("✅ Database tables initialized")
        except Error as e:
            logger.error(f"❌ Database initialization error: {e}")
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def create_device_sensor_table(self, device_id):
        """Create a sensor data table for a specific device"""
        conn = self.get_connection()
        if not conn: return False
        
        try:
            cursor = conn.cursor()
            table_name = f"sensor_data_{device_id.replace('-', '_').replace('.', '_')}"
            
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    temperature FLOAT,
                    humidity FLOAT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            logger.info(f"✅ Created sensor table for device: {device_id}")
            return True
        except Error as e:
            logger.error(f"❌ Error creating sensor table for {device_id}: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    
    def add_device(self, device_id, name, room, ip, port=502):
        """Add a new device to database"""
        conn = self.get_connection()
        if not conn: return False
        
        try:
            cursor = conn.cursor()
            
            # Check if device already exists
            cursor.execute("SELECT device_id FROM devices WHERE device_id = %s", (device_id,))
            if cursor.fetchone():
                logger.info(f"Device {device_id} already exists")
                return True
            
            # Insert new device
            cursor.execute("""
                INSERT INTO devices (device_id, name, room, ip, port)
                VALUES (%s, %s, %s, %s, %s)
            """, (device_id, name, room, ip, port))
            
            conn.commit()
            
            # Create sensor table for this device
            self.create_device_sensor_table(device_id)
            
            logger.info(f"✅ Added device to database: {device_id}")
            return True
        except Error as e:
            logger.error(f"❌ Error adding device {device_id}: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    
    def remove_device(self, device_id):
        """Remove a device and its sensor table"""
        conn = self.get_connection()
        if not conn: return False
        
        try:
            cursor = conn.cursor()
            
            # Drop sensor table
            table_name = f"sensor_data_{device_id.replace('-', '_').replace('.', '_')}"
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            
            # Delete device (cascade will delete events)
            cursor.execute("DELETE FROM devices WHERE device_id = %s", (device_id,))
            
            conn.commit()
            logger.info(f"✅ Removed device from database: {device_id}")
            return True
        except Error as e:
            logger.error(f"❌ Error removing device {device_id}: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    
    def update_device_status(self, device_id, connected=True):
        """Update device connection status"""
        conn = self.get_connection()
        if not conn: return False
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE devices 
                SET connected = %s, last_seen = %s 
                WHERE device_id = %s
            """, (connected, datetime.now(), device_id))
            conn.commit()
            return True
        except Error as e:
            logger.error(f"❌ Error updating device status: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    
    def update_device_thresholds(self, device_id, thresholds):
        """Update device thresholds"""
        conn = self.get_connection()
        if not conn: return False
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE devices 
                SET temp_threshold = %s,
                    humidity_threshold = %s,
                    buzzer_temp_threshold = %s,
                    buzzer_humidity_threshold = %s
                WHERE device_id = %s
            """, (
                thresholds.get('temp_threshold', 30.0),
                thresholds.get('humidity_threshold', 70.0),
                thresholds.get('buzzer_temp_threshold', 35.0),
                thresholds.get('buzzer_humidity_threshold', 80.0),
                device_id
            ))
            conn.commit()
            return True
        except Error as e:
            logger.error(f"❌ Error updating thresholds: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    
    def get_devices(self):
        """Get all devices from database"""
        conn = self.get_connection()
        if not conn: return []
        
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM devices ORDER BY created_at DESC")
            devices = cursor.fetchall()
            return devices
        except Error as e:
            logger.error(f"❌ Error getting devices: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    
    def get_device(self, device_id):
        """Get specific device by ID"""
        conn = self.get_connection()
        if not conn: return None
        
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM devices WHERE device_id = %s", (device_id,))
            device = cursor.fetchone()
            return device
        except Error as e:
            logger.error(f"❌ Error getting device: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    
    def add_sensor_reading(self, device_id, temperature, humidity):
        """Add sensor reading to device's sensor table (maintains last 10 records)"""
        conn = self.get_connection()
        if not conn: return False
        
        try:
            cursor = conn.cursor()
            table_name = f"sensor_data_{device_id.replace('-', '_').replace('.', '_')}"
            
            # Insert new reading
            cursor.execute(f"""
                INSERT INTO {table_name} (temperature, humidity, timestamp)
                VALUES (%s, %s, %s)
            """, (temperature, humidity, datetime.now()))
            
            # Get count of records
            cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            count = cursor.fetchone()[0]
            
            # If more than 10 records, delete the oldest one(s)
            if count > 10:
                delete_count = count - 10
                cursor.execute(f"""
                    DELETE FROM {table_name} 
                    ORDER BY timestamp ASC 
                    LIMIT %s
                """, (delete_count,))
            
            conn.commit()
            return True
        except Error as e:
            logger.error(f"❌ Error adding sensor reading for {device_id}: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    
    def get_sensor_history(self, device_id, limit=10):
        """Get last N sensor readings for a device (most recent first)"""
        conn = self.get_connection()
        if not conn: return []
        
        try:
            cursor = conn.cursor(dictionary=True)
            table_name = f"sensor_data_{device_id.replace('-', '_').replace('.', '_')}"
            
            cursor.execute(f"""
                SELECT temperature, humidity, timestamp 
                FROM {table_name} 
                ORDER BY timestamp DESC 
                LIMIT %s
            """, (limit,))
            
            readings = cursor.fetchall()
            
            # Return in chronological order (oldest first for chart)
            return list(reversed(readings))
        except Error as e:
            logger.error(f"❌ Error getting sensor history for {device_id}: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    
    def add_event(self, device_id, event_type, description):
        """Add an event to the events table"""
        conn = self.get_connection()
        if not conn: return False
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO events (device_id, event_type, description, timestamp)
                VALUES (%s, %s, %s, %s)
            """, (device_id, event_type, description, datetime.now()))
            conn.commit()
            return True
        except Error as e:
            logger.error(f"❌ Error adding event: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    
    def get_events(self, device_id=None, limit=50):
        """Get events for a specific device or all devices"""
        conn = self.get_connection()
        if not conn: return []
        
        try:
            cursor = conn.cursor(dictionary=True)
            
            if device_id:
                cursor.execute("""
                    SELECT * FROM events 
                    WHERE device_id = %s 
                    ORDER BY timestamp DESC 
                    LIMIT %s
                """, (device_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM events 
                    ORDER BY timestamp DESC 
                    LIMIT %s
                """, (limit,))
            
            events = cursor.fetchall()
            return events
        except Error as e:
            logger.error(f"❌ Error getting events: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    
    def close(self):
        """No-op as we use a connection pool"""
        pass