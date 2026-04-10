from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from modbus_client import ModbusClient
from control_logic import ControlLogic
from network_scanner import NetworkScanner
from device_manager import DeviceManager
import logging
from datetime import datetime
import threading
import subprocess
import atexit

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, 
            static_folder='../frontend',
            static_url_path='')
CORS(app)

# Initialize components
# Initialize DeviceManager with MySQL configuration 
db_config = { 
    'host': 'localhost', 
    'user': 'root', 
    'password': 'Veejnas@4002',  # YOUR MYSQL PASSWORD HERE 
    'database': 'scada_db' 
} 
device_manager = DeviceManager(db_config=db_config) 
scanner = NetworkScanner()

# Store Modbus clients and control logic for each device (independent)
modbus_clients = {}
control_logics = {}

# Store independent monitoring threads for each device
monitoring_threads = {}
monitoring_active = {}

# ============== STATIC FILE ROUTES ==============

@app.route('/')
def serve_index():
    return send_from_directory('../frontend', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('../frontend', path)

# ============== NETWORK DISCOVERY ==============

@app.route('/api/network/info', methods=['GET'])
def get_network_info():
    """Get local network information"""
    return jsonify({
        'local_ip': scanner.local_ip,
        'network': scanner.network,
        'gateway': '.'.join(scanner.local_ip.split('.')[:-1]) + '.1'
    })

@app.route('/api/network/scan', methods=['POST'])
def scan_network():
    """Scan network for all devices"""
    data = request.json or {}
    scan_type = data.get('type', 'quick')
    
    logger.info(f"🔍 Scan request received: type={scan_type}")
    
    try:
        if scan_type == 'quick':
            logger.info("Starting quick scan...")
            devices = scanner.quick_scan()
        else:
            logger.info("Starting full network scan...")
            devices = scanner.scan_network()
        
        logger.info(f"✅ Scan complete. Found {len(devices)} device(s)")
        
        # Add to device manager if they're ESP32 devices
        for device in devices:
            if device.get('is_esp32') or device.get('device_type') == 'ESP32':
                device_id = device.get('device_id', f"esp32_{device['ip'].replace('.', '_')}")
                device_manager.add_device(
                    device_id=device_id,
                    ip=device['ip'],
                    port=device.get('port', 502),
                    room=device.get('hostname', device_id),
                    name=device.get('hostname', device_id)
                )
        
        return jsonify({
            'status': 'success',
            'devices': devices,
            'count': len(devices),
            'scan_type': scan_type
        })
    except Exception as e:
        logger.error(f"Scan error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ============== DEVICE MANAGEMENT ==============

@app.route('/api/devices', methods=['GET'])
def get_devices():
    """Get all devices with their independent status
    
    Query Parameters:
        connected_only: If 'true', only returns connected devices (default: false)
    """
    connected_only = request.args.get('connected_only', 'false').lower() == 'true'
    devices = device_manager.get_device_list(include_disconnected=not connected_only)
    
    # Add real-time status for each device from its control logic
    for device in devices:
        device_id = device['id']
        if device_id in control_logics:
            try:
                status = control_logics[device_id].get_status()
                device['temperature'] = status.get('temperature')
                device['humidity'] = status.get('humidity')
                device['temp_led_state'] = status.get('temp_led_state', False)
                device['humidity_led_state'] = status.get('humidity_led_state', False)
                device['buzzer_state'] = status.get('buzzer_state', False)
                device['manual_temp_led'] = status.get('manual_temp_led')
                device['manual_humidity_led'] = status.get('manual_humidity_led')
                device['manual_buzzer'] = status.get('manual_buzzer')
                device['monitoring_active'] = monitoring_active.get(device_id, False)
            except Exception as e:
                logger.error(f"Error getting status for {device_id}: {e}")
    
    return jsonify(devices)

@app.route('/api/devices', methods=['POST'])
def add_device():
    """Add a new device manually"""
    data = request.json
    device_id = data.get('device_id')
    ip = data.get('ip')
    port = data.get('port', 502)
    room = data.get('room', device_id)
    name = data.get('name', room)
    
    if not device_id or not ip:
        return jsonify({'status': 'error', 'message': 'Device ID and IP required'}), 400
    
    success = device_manager.add_device(device_id, ip, port, room, name)
    if success:
        return jsonify({'status': 'success', 'message': f'Device {device_id} added'})
    return jsonify({'status': 'error', 'message': 'Device already exists'}), 400

@app.route('/api/devices/<device_id>', methods=['DELETE'])
def remove_device(device_id):
    """Remove a device"""
    # Stop monitoring if active
    if device_id in monitoring_active and monitoring_active[device_id]:
        stop_device_monitoring(device_id)
    
    success = device_manager.remove_device(device_id)
    if success:
        # Clean up control logic and modbus client
        if device_id in control_logics:
            try:
                control_logics[device_id].stop()
            except:
                pass
            del control_logics[device_id]
        
        if device_id in modbus_clients:
            try:
                modbus_clients[device_id].disconnect()
            except:
                pass
            del modbus_clients[device_id]
        
        return jsonify({'status': 'success', 'message': f'Device {device_id} removed'})
    return jsonify({'status': 'error', 'message': 'Device not found'}), 404

@app.route('/api/devices/<device_id>/connect', methods=['POST'])
def connect_device(device_id):
    """Connect to a specific device (independent connection)"""
    device = device_manager.get_device(device_id)
    if not device:
        return jsonify({'status': 'error', 'message': 'Device not found'}), 404
    
    # Create independent Modbus client for this device
    from modbus_client import ModbusClient
    modbus_client = ModbusClient()
    success, message = modbus_client.connect(device['ip'], device['port'])
    
    if success:
        modbus_clients[device_id] = modbus_client
        
        # Create independent control logic for this device
        from control_logic import ControlLogic
        control_logic = ControlLogic(modbus_client)
        
        # Load saved thresholds from database
        db_device = device_manager.db.get_device(device_id)
        if db_device:
            control_logic.set_thresholds(
                temp=db_device.get('temp_threshold', 30.0),
                humidity=db_device.get('humidity_threshold', 70.0),
                buzzer_temp=db_device.get('buzzer_temp_threshold', 35.0),
                buzzer_humidity=db_device.get('buzzer_humidity_threshold', 80.0)
            )
        
        control_logics[device_id] = control_logic
        
        device_manager.update_device_data(device_id, {
            'connected': True,
            'modbus_client': modbus_client,
            'control_logic': control_logic
        })
        
        device_manager.add_device_event(device_id, 'CONNECTION', f'Connected to {device["ip"]}:{device["port"]}')
        
        return jsonify({'status': 'success', 'message': f'Connected to {device_id}'})
    
    return jsonify({'status': 'error', 'message': message}), 500

@app.route('/api/devices/<device_id>/disconnect', methods=['POST'])
def disconnect_device(device_id):
    """Disconnect from a specific device"""
    device = device_manager.get_device(device_id)
    if not device:
        return jsonify({'status': 'error', 'message': 'Device not found'}), 404
    
    # Stop monitoring if active
    if device_id in monitoring_active and monitoring_active[device_id]:
        stop_device_monitoring(device_id)
    
    if device_id in modbus_clients:
        try:
            modbus_clients[device_id].disconnect()
        except:
            pass
        del modbus_clients[device_id]
    
    if device_id in control_logics:
        try:
            control_logics[device_id].stop()
        except:
            pass
        del control_logics[device_id]
    
    device_manager.update_device_data(device_id, {'connected': False})
    device_manager.add_device_event(device_id, 'CONNECTION', 'Disconnected')
    
    return jsonify({'status': 'success', 'message': f'Disconnected from {device_id}'})

# ============== INDEPENDENT DEVICE CONTROL ==============

def start_device_monitoring(device_id):
    """Start independent monitoring for a specific device"""
    if device_id not in control_logics:
        return False, "Device not connected"
    
    if monitoring_active.get(device_id, False):
        return False, "Monitoring already active"
    
    success = control_logics[device_id].start()
    if success:
        monitoring_active[device_id] = True
        device_manager.add_device_event(device_id, 'SYSTEM', 'Monitoring started')
        
        # Start a background thread to update database with sensor readings
        def update_sensor_data():
            import time
            while monitoring_active.get(device_id, False):
                try:
                    # Check if control logic is still running
                    if not control_logics[device_id].running:
                        logger.warning(f"⚠️ Control logic for {device_id} stopped. Terminating monitoring thread.")
                        monitoring_active[device_id] = False
                        
                        # Update device manager connection status
                        device_manager.update_device_data(device_id, {'connected': False})
                        device_manager.add_device_event(device_id, 'ERROR', 'Connection lost - Monitoring terminated')
                        break
                        
                    status = control_logics[device_id].get_status()
                    temp = status.get('temperature')
                    humidity = status.get('humidity')
                    
                    if temp is not None and humidity is not None:
                        device_manager.add_sensor_reading(device_id, temp, humidity)
                    else:
                        # If no reading for a while, we could potentially stop it too
                        # But for now, let's rely on the control loop's connection check
                        pass
                    
                    # Update device thresholds in database if changed
                    device_manager.update_device_data(device_id, {
                        'temp_threshold': status.get('temp_threshold', 30.0),
                        'humidity_threshold': status.get('humidity_threshold', 70.0),
                        'buzzer_temp_threshold': status.get('buzzer_temp_threshold', 35.0),
                        'buzzer_humidity_threshold': status.get('buzzer_humidity_threshold', 80.0)
                    })
                    
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Error updating sensor data for {device_id}: {e}")
                    time.sleep(2)
            
            logger.info(f"Monitoring thread for {device_id} finished.")
        
        thread = threading.Thread(target=update_sensor_data, daemon=True)
        monitoring_threads[device_id] = thread
        thread.start()
        
        return True, "Monitoring started"
    
    return False, "Failed to start monitoring"

def stop_device_monitoring(device_id):
    """Stop independent monitoring for a specific device"""
    if device_id in control_logics:
        control_logics[device_id].stop()
    
    monitoring_active[device_id] = False
    
    if device_id in monitoring_threads:
        monitoring_threads[device_id] = None
    
    device_manager.add_device_event(device_id, 'SYSTEM', 'Monitoring stopped')
    return True

@app.route('/api/devices/<device_id>/start', methods=['POST'])
def start_device(device_id):
    """Start monitoring for a specific device"""
    success, message = start_device_monitoring(device_id)
    if success:
        return jsonify({'status': 'success', 'message': message})
    return jsonify({'status': 'error', 'message': message}), 400

@app.route('/api/devices/<device_id>/stop', methods=['POST'])
def stop_device(device_id):
    """Stop monitoring for a specific device"""
    success = stop_device_monitoring(device_id)
    return jsonify({'status': 'success', 'message': 'Monitoring stopped'})

@app.route('/api/devices/<device_id>/status', methods=['GET'])
def get_device_status(device_id):
    """Get independent status for a specific device"""
    if device_id not in control_logics:
        return jsonify({
            'status': 'disconnected',
            'temperature': None,
            'humidity': None,
            'temp_led_state': False,
            'humidity_led_state': False,
            'buzzer_state': False,
            'monitoring_active': False
        }), 200
    
    try:
        status = control_logics[device_id].get_status()
        status['monitoring_active'] = monitoring_active.get(device_id, False)
        status['device_id'] = device_id
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error getting status for {device_id}: {e}")
        return jsonify({
            'status': 'error',
            'temperature': None,
            'humidity': None,
            'temp_led_state': False,
            'humidity_led_state': False,
            'buzzer_state': False,
            'monitoring_active': False
        }), 500

# ============== INDEPENDENT THRESHOLD MANAGEMENT ==============

@app.route('/api/devices/<device_id>/thresholds', methods=['GET'])
def get_device_thresholds(device_id):
    """Get thresholds for a specific device"""
    if device_id not in control_logics:
        return jsonify({'status': 'error', 'message': 'Device not connected'}), 400
    
    status = control_logics[device_id].get_status()
    return jsonify({
        'temp_threshold': status.get('temp_threshold', 30.0),
        'humidity_threshold': status.get('humidity_threshold', 70.0),
        'buzzer_temp_threshold': status.get('buzzer_temp_threshold', 35.0),
        'buzzer_humidity_threshold': status.get('buzzer_humidity_threshold', 80.0)
    })

@app.route('/api/devices/<device_id>/thresholds', methods=['POST'])
def set_device_thresholds(device_id):
    """Set thresholds for a specific device (independent)"""
    if device_id not in control_logics:
        return jsonify({'status': 'error', 'message': 'Device not connected'}), 400
    
    data = request.json
    control_logics[device_id].set_thresholds(
        temp=data.get('temp_threshold'),
        humidity=data.get('humidity_threshold'),
        buzzer_temp=data.get('buzzer_temp_threshold'),
        buzzer_humidity=data.get('buzzer_humidity_threshold')
    )
    
    # Save to database
    device_manager.db.update_device_thresholds(device_id, {
        'temp_threshold': data.get('temp_threshold', 30.0),
        'humidity_threshold': data.get('humidity_threshold', 70.0),
        'buzzer_temp_threshold': data.get('buzzer_temp_threshold', 35.0),
        'buzzer_humidity_threshold': data.get('buzzer_humidity_threshold', 80.0)
    })
    
    device_manager.add_device_event(device_id, 'CONFIG', 'Thresholds updated')
    return jsonify({'status': 'success', 'message': 'Thresholds updated'})

# ============== INDEPENDENT MANUAL CONTROL ==============

@app.route('/api/devices/<device_id>/control/<device>', methods=['POST'])
def manual_control_device(device_id, device):
    """Manual control for a specific device (independent)"""
    if device_id not in control_logics:
        return jsonify({'status': 'error', 'message': 'Device not connected'}), 400
    
    data = request.json
    state = data.get('state')
    
    valid_devices = ['temp_led', 'humidity_led', 'buzzer']
    if device not in valid_devices:
        return jsonify({'status': 'error', 'message': 'Invalid device'}), 400
    
    control_logics[device_id].set_manual_control(device, state)
    
    state_text = 'ON' if state else 'OFF' if state is not None else 'AUTO'
    device_manager.add_device_event(device_id, 'MANUAL', f'{device} set to {state_text}')
    
    return jsonify({'status': 'success', 'message': f'{device} set to {state_text}'})

@app.route('/api/devices/<device_id>/control/auto/<device>', methods=['POST'])
def auto_control_device(device_id, device):
    """Return specific device to automatic control (independent)"""
    if device_id not in control_logics:
        return jsonify({'status': 'error', 'message': 'Device not connected'}), 400
    
    valid_devices = ['temp_led', 'humidity_led', 'buzzer', 'all']
    if device not in valid_devices:
        return jsonify({'status': 'error', 'message': 'Invalid device'}), 400
    
    if device == 'all':
        control_logics[device_id].reset_manual()
    else:
        control_logics[device_id].reset_manual(device)
    
    device_manager.add_device_event(device_id, 'SYSTEM', f'{device} returned to auto mode')
    return jsonify({'status': 'success', 'message': f'{device} returned to auto mode'})

# ============== INDEPENDENT DATA RETRIEVAL ==============

@app.route('/api/devices/<device_id>/history', methods=['GET'])
def get_device_history(device_id):
    """Get sensor history for a specific device from MySQL"""
    limit = request.args.get('limit', 10, type=int)
    data = device_manager.get_sensor_history(device_id, limit)
    return jsonify(data)

@app.route('/api/devices/<device_id>/events', methods=['GET'])
def get_device_events(device_id):
    """Get events for a specific device"""
    limit = request.args.get('limit', 50, type=int)
    data = device_manager.get_device_events(device_id, limit)
    return jsonify(data)

@app.route('/api/devices/<device_id>/buffer/clear', methods=['POST'])
def clear_device_buffer(device_id):
    """Clear sensor buffer for a specific device"""
    if device_id not in control_logics:
        return jsonify({'status': 'error', 'message': 'Device not connected'}), 400
    
    # Clear MySQL sensor data for this device
    table_name = f"sensor_data_{device_id.replace('-', '_').replace('.', '_')}"
    try:
        cursor = device_manager.db.connection.cursor()
        cursor.execute(f"TRUNCATE TABLE {table_name}")
        device_manager.db.connection.commit()
        cursor.close()
        
        device_manager.add_device_event(device_id, 'SYSTEM', 'Buffer cleared')
        return jsonify({'status': 'success', 'message': 'Buffer cleared'})
    except Exception as e:
        logger.error(f"Error clearing buffer for {device_id}: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ============== LEGACY ENDPOINTS (for backward compatibility) ==============
# These are kept for the single-device view mode

@app.route('/api/status', methods=['GET'])
def get_status():
    """Legacy: Get status of active device (for single-device view)"""
    active_device = device_manager.get_active_device()
    if not active_device:
        return jsonify({
            'status': 'disconnected',
            'temperature': None,
            'humidity': None,
            'temp_led_state': False,
            'humidity_led_state': False,
            'buzzer_state': False,
            'message': 'No active device'
        }), 200
    
    return get_device_status(active_device)

@app.route('/api/thresholds', methods=['POST'])
def set_thresholds():
    """Legacy: Set thresholds for active device"""
    active_device = device_manager.get_active_device()
    if not active_device:
        return jsonify({'status': 'error', 'message': 'No active device selected'}), 400
    
    data = request.json
    return set_device_thresholds(active_device)

@app.route('/api/control/<device>', methods=['POST'])
def manual_control(device):
    """Legacy: Manual control for active device"""
    active_device = device_manager.get_active_device()
    if not active_device:
        return jsonify({'status': 'error', 'message': 'No active device selected'}), 400
    
    return manual_control_device(active_device, device)

@app.route('/api/control/auto/<device>', methods=['POST'])
def auto_control(device):
    """Legacy: Auto control for active device"""
    active_device = device_manager.get_active_device()
    if not active_device:
        return jsonify({'status': 'error', 'message': 'No active device selected'}), 400
    
    return auto_control_device(active_device, device)

@app.route('/api/system/start', methods=['POST'])
def start_system():
    """Legacy: Start system for active device"""
    active_device = device_manager.get_active_device()
    if not active_device:
        return jsonify({'status': 'error', 'message': 'No active device selected'}), 400
    
    return start_device(active_device)

@app.route('/api/system/stop', methods=['POST'])
def stop_system():
    """Legacy: Stop system for active device"""
    active_device = device_manager.get_active_device()
    if not active_device:
        return jsonify({'status': 'error', 'message': 'No active device selected'}), 400
    
    return stop_device(active_device)

@app.route('/api/sensors/history', methods=['GET'])
def get_sensor_history():
    """Legacy: Get sensor history for active device"""
    active_device = device_manager.get_active_device()
    if not active_device:
        return jsonify([])
    
    return get_device_history(active_device)

@app.route('/api/events', methods=['GET'])
def get_events():
    """Legacy: Get events for active device"""
    active_device = device_manager.get_active_device()
    if not active_device:
        return jsonify([])
    
    return get_device_events(active_device)

@app.route('/api/events/all', methods=['GET'])
def get_all_events():
    """Get events from all devices"""
    return jsonify(device_manager.get_all_events())

@app.route('/api/buffer/clear', methods=['POST'])
def clear_buffer():
    """Legacy: Clear buffer for active device"""
    active_device = device_manager.get_active_device()
    if not active_device:
        return jsonify({'status': 'error', 'message': 'No active device selected'}), 400
    
    return clear_device_buffer(active_device)

@app.route('/api/devices/active', methods=['GET'])
def get_active_device():
    """Get active device"""
    active = device_manager.get_active_device()
    return jsonify({'active_device': active})

@app.route('/api/devices/<device_id>/active', methods=['POST'])
def set_active_device(device_id):
    """Set active device for control
    
    Only allows setting connected devices as active.
    """
    device = device_manager.get_device(device_id)
    if not device:
        return jsonify({'status': 'error', 'message': 'Device not found'}), 404
    
    # Check if device is connected
    if not device.get('connected', False):
        return jsonify({
            'status': 'error', 
            'message': f'Device "{device.get("room", device_id)}" is not available. Please connect it first.'
        }), 400
    
    success = device_manager.set_active_device(device_id)
    if success:
        return jsonify({'status': 'success', 'message': f'Active device: {device_id}'})
    return jsonify({'status': 'error', 'message': 'Failed to set active device'}), 500

@app.route('/api/ping', methods=['GET'])
def ping():
    """Simple ping endpoint"""
    return jsonify({
        'status': 'online',
        'timestamp': datetime.now().isoformat(),
        'active_device': device_manager.get_active_device()
    })

if __name__ == '__main__':
    from waitress import serve
    
    logger.info("=" * 60)
    logger.info("🚀 Multi-ESP32 SCADA Monitoring System Starting...")
    logger.info("📊 Frontend: http://localhost:5001")
    logger.info(f"🌐 Local IP: {scanner.local_ip}")
    logger.info(f"🌐 Network: {scanner.network}")
    logger.info("🔌 Multi-Device Support: Active (Independent Control)")
    logger.info("🔍 Network Discovery: Active")
    logger.info("💾 Storage: MySQL Database (10 readings per device)")
    
    # --- CLOUDFLARED TUNNEL STARTUP ---
    tunnel_process = None
    try:
        # Using full path to ensure it's found
        cloudflared_path = "/opt/homebrew/bin/cloudflared"
        
        logger.info(f"☁️ Starting cloudflared tunnel at {cloudflared_path}: nextjs-live...")
        
        # Check if the binary exists
        import os
        if not os.path.exists(cloudflared_path):
            # Fallback to searching in PATH if brew path doesn't exist
            cloudflared_path = "cloudflared"
            logger.warning(f"⚠️ {cloudflared_path} not found at standard Brew path. Falling back to PATH.")

        # Running in background and suppressing output for clarity
        tunnel_process = subprocess.Popen(
            [cloudflared_path, "tunnel", "run", "nextjs-live"], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        
        # Check if process actually started
        import time
        time.sleep(1)
        if tunnel_process.poll() is None:
            logger.info("✅ Tunnel process successfully initiated and running.")
        else:
            return_code = tunnel_process.returncode
            logger.error(f"❌ Tunnel process exited immediately with return code: {return_code}")
        
        # Cleanup when the Flask process exits
        @atexit.register
        def cleanup_tunnel():
            if tunnel_process and tunnel_process.poll() is None:
                logger.info("🛑 Stopping cloudflared tunnel...")
                tunnel_process.terminate()
                try:
                    tunnel_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    tunnel_process.kill()
                
    except Exception as e:
        logger.error(f"❌ Failed to start cloudflared tunnel: {e}")
    # -----------------------------------
    
    logger.info("=" * 60)
    
    serve(app, host='0.0.0.0', port=5001)