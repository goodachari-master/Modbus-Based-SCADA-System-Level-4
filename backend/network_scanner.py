import socket
import ipaddress
import subprocess
import threading
import time
from datetime import datetime
import logging
from pymodbus.client import ModbusTcpClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NetworkScanner:
    def __init__(self):
        self.devices = []
        self.scanning = False
        self.local_ip = self.get_local_ip()
        self.network = self.get_network_range()
        
    def get_local_ip(self):
        """Get local IP address of this machine"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception as e:
            logger.error(f"Error getting local IP: {e}")
            return "192.168.1.100"
    
    def get_network_range(self):
        """Get network range based on local IP"""
        try:
            ip_parts = self.local_ip.split('.')
            network_base = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}"
            return f"{network_base}.1/24"
        except Exception as e:
            logger.error(f"Error getting network range: {e}")
            return "192.168.1.0/24"
    
    def ping_host(self, ip):
        """Ping a host to check if it's alive"""
        try:
            import platform
            param = '-n' if platform.system().lower() == 'windows' else '-c'
            command = ['ping', param, '1', '-W', '1', ip]
            result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return result.returncode == 0
        except:
            return False
    
    def get_hostname(self, ip):
        """Get hostname from IP address"""
        try:
            hostname = socket.gethostbyaddr(ip)[0]
            return hostname
        except:
            return "Unknown"
    
    def get_device_type(self, hostname, ip, open_ports):
        """Determine device type based on hostname, IP, and open ports"""
        hostname_lower = hostname.lower()
        
        # Check for ESP32 (Modbus port 502 open)
        if 502 in [p['port'] for p in open_ports]:
            return 'ESP32'
        
        if 'esp' in hostname_lower or 'esp32' in hostname_lower:
            return 'ESP32'
        
        mobile_keywords = ['iphone', 'ipad', 'android', 'mobile', 'phone', 'tab', 'galaxy', 'pixel']
        if any(keyword in hostname_lower for keyword in mobile_keywords):
            return 'Mobile'
        
        computer_keywords = ['laptop', 'pc', 'desktop', 'computer', 'macbook', 'thinkpad', 'dell', 'hp', 'lenovo']
        if any(keyword in hostname_lower for keyword in computer_keywords):
            return 'Computer'
        
        router_keywords = ['router', 'gateway', 'ap', 'accesspoint', 'wifi']
        if any(keyword in hostname_lower for keyword in router_keywords):
            return 'Router'
        
        return 'Unknown'
    
    def get_room_from_mdns(self, ip):
        """Try to get room name via mDNS"""
        try:
            # This is simplified - in practice would need mDNS query
            # For now, return None
            return None
        except:
            return None
    
    def get_room_from_modbus(self, ip, port=502, timeout=2.0):
        """Read room name from ESP32 Modbus holding registers"""
        try:
            logger.debug(f"📡 Attempting to read room name from {ip}:{port}")
            client = ModbusTcpClient(ip, port=port)
            client.timeout = timeout
            
            if not client.connect():
                logger.debug(f"❌ Could not connect to {ip}:{port} for Modbus")
                return None
            
            logger.debug(f"✅ Connected to {ip}, reading room name from register 10")
            
            # Read room name from holding registers starting at register 10
            # Room name is stored as ASCII characters in consecutive registers
            room_chars = []
            for reg_addr in range(10, 26):  # Read up to 16 characters
                try:
                    result = client.read_holding_registers(reg_addr, 1)
                    if result.isError():
                        logger.debug(f"⚠️ Error reading register {reg_addr}")
                        break
                    
                    char_code = result.registers[0]
                    logger.debug(f"  Register {reg_addr}: {char_code} = '{chr(char_code) if 32 <= char_code <= 126 else '?'}'")
                    
                    if char_code == 0:  # Null terminator
                        break
                    
                    if 32 <= char_code <= 126:  # Printable ASCII
                        room_chars.append(chr(char_code))
                    else:
                        # Non-printable character, might be end of string
                        break
                except Exception as e:
                    logger.debug(f"⚠️ Exception reading register {reg_addr}: {e}")
                    break
            
            client.close()
            
            if room_chars:
                room_name = ''.join(room_chars).strip()
                logger.info(f"✅ Read room name from {ip}: '{room_name}'")
                return room_name
            else:
                logger.debug(f"⚠️ No valid room name characters read from {ip}")
                return None
                
        except Exception as e:
            logger.debug(f"❌ Failed to read room name from {ip}: {e}")
            return None
    
    def scan_port(self, ip, port, timeout=1):
        """Check if a specific port is open on the host"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except:
            return False
    
    def scan_device(self, ip):
        """Scan a single device for detailed information"""
        if not self.ping_host(ip):
            return None
        
        hostname = self.get_hostname(ip)
        
        # Check for common ports
        ports = {
            502: 'Modbus',
            80: 'HTTP',
            443: 'HTTPS',
            22: 'SSH',
            21: 'FTP',
            8080: 'HTTP-Alt',
            1883: 'MQTT',
            8883: 'MQTT-TLS'
        }
        
        open_ports = []
        for port, service in ports.items():
            if self.scan_port(ip, port, timeout=0.5):
                open_ports.append({'port': port, 'service': service})
        
        device_type = self.get_device_type(hostname, ip, open_ports)
        
        # Generate device ID from hostname or IP
        if device_type == 'ESP32':
            # Try to get room name from mDNS or use IP
            room = self.get_room_from_mdns(ip) or f"ESP32_{ip.replace('.', '_')}"
            device_id = room.lower().replace(' ', '_')
        else:
            device_id = hostname.lower().replace(' ', '_').replace('.', '_')
        
        device_info = {
            'ip': ip,
            'hostname': hostname,
            'device_type': device_type,
            'device_id': device_id,
            'open_ports': open_ports,
            'last_seen': datetime.now().isoformat(),
            'is_esp32': device_type == 'ESP32' or 502 in [p['port'] for p in open_ports],
            'port': 502 if 502 in [p['port'] for p in open_ports] else None
        }
        
        return device_info
    
    def scan_network(self, progress_callback=None):
        """Scan entire network for devices"""
        self.scanning = True
        self.devices = []
        
        logger.info(f"Starting network scan on {self.network}")
        
        try:
            network = ipaddress.ip_network(self.network, strict=False)
            total_hosts = network.num_addresses
            scanned = 0
            
            for ip in network.hosts():
                if not self.scanning:
                    break
                
                ip_str = str(ip)
                if ip_str.endswith('.1') or ip_str.endswith('.255'):
                    continue
                
                device_info = self.scan_device(ip_str)
                if device_info:
                    self.devices.append(device_info)
                    logger.info(f"Found device: {ip_str} - {device_info['hostname']} ({device_info['device_type']})")
                
                scanned += 1
                if progress_callback:
                    progress = (scanned / total_hosts) * 100
                    progress_callback(progress)
                
                time.sleep(0.05)
            
        except Exception as e:
            logger.error(f"Network scan error: {e}")
        finally:
            self.scanning = False
            logger.info(f"Network scan complete. Found {len(self.devices)} devices")
        
        return self.devices
    
    def quick_scan(self):
        """Quick scan for ESP32 devices only (checks port 502)"""
        esp_devices = []
        logger.info("Starting quick scan for ESP32 devices...")
        logger.info(f"Scanning network: {self.network}")
        logger.info(f"Local IP: {self.local_ip}")
        
        try:
            network = ipaddress.ip_network(self.network, strict=False)
            total_hosts = network.num_addresses - 2  # Exclude network and broadcast
            logger.info(f"Will scan {total_hosts} hosts for Modbus port 502")
            scanned_count = 0
            found_count = 0
            checked_ips = []
            
            for ip in network.hosts():
                ip_str = str(ip)
                if ip_str.endswith('.1') or ip_str.endswith('.255'):
                    continue
                
                # Check if Modbus port (502) is open
                try:
                    port_open = self.scan_port(ip_str, 502, timeout=0.3)
                    if port_open:
                        logger.info(f"🔍 Found device with port 502 open at {ip_str}")
                        
                        # Try to read room name from Modbus
                        room_name = self.get_room_from_modbus(ip_str)
                        
                        hostname = self.get_hostname(ip_str)
                        
                        # Use room name from Modbus or fallback to hostname/IP
                        if room_name:
                            display_name = room_name
                            device_id = room_name.lower().replace(' ', '_').replace('.', '_')
                        else:
                            display_name = hostname
                            device_id = f"esp32_{ip_str.replace('.', '_')}"
                        
                        device_info = {
                            'ip': ip_str,
                            'hostname': display_name,
                            'device_type': 'ESP32',
                            'device_id': device_id,
                            'port': 502,
                            'room': room_name or display_name,
                            'name': room_name or display_name,
                            'last_seen': datetime.now().isoformat(),
                            'is_esp32': True
                        }
                        esp_devices.append(device_info)
                        found_count += 1
                        logger.info(f"✅ FOUND ESP32 at {ip_str} - Room: '{room_name or 'Unknown'}' (ID: {device_id})")
                    else:
                        scanned_count += 1
                        # Log first 10 IPs checked for debugging
                        if scanned_count <= 10:
                            checked_ips.append(ip_str)
                        elif scanned_count % 50 == 0:
                            logger.debug(f"Checked {scanned_count}/{total_hosts} hosts... ({found_count} found so far)")
                except Exception as e:
                    logger.warning(f"Error scanning {ip_str}: {e}")
                
        except Exception as e:
            logger.error(f"❌ Quick scan error: {e}", exc_info=True)
        
        logger.info(f"Quick scan complete. Found {found_count} ESP32 device(s) out of {scanned_count} hosts scanned")
        if len(esp_devices) == 0:
            logger.warning("No ESP32 devices found.")
            if checked_ips:
                logger.info(f"First 10 IPs checked: {', '.join(checked_ips)}")
            logger.warning("TROUBLESHOOTING STEPS:")
            logger.warning("  1. Check ESP32 serial monitor to confirm it's connected to WiFi")
            logger.warning(f"  2. Verify ESP32 IP address (should be in {self.network} range)")
            logger.warning("  3. Check if ESP32 Modbus server is running (port 502)")
            logger.warning("  4. Try pinging ESP32 from terminal: ping <ESP32_IP>")
            logger.warning("  5. Check macOS firewall settings")
            logger.warning("  6. Try manually adding device with known IP")
        
        return esp_devices
    
    def stop_scan(self):
        """Stop ongoing scan"""
        self.scanning = False
        logger.info("Network scan stopped by user")