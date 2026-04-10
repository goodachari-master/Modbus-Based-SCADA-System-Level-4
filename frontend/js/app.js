// Global variables
console.log('🚀 app.js loaded!');

// Independent device control functions 
 
 // Start monitoring for a specific device 
 async function startDeviceMonitoring(deviceId) { 
     try { 
         const response = await fetch(`/api/devices/${deviceId}/start`, { 
             method: 'POST' 
         }); 
         const data = await response.json(); 
         
         if (response.ok) { 
             showNotification(`Monitoring started for ${deviceId}`, 'success'); 
             return true; 
         } else { 
             showNotification(data.message, 'error'); 
             return false; 
         } 
     } catch (error) { 
         console.error('Start monitoring error:', error); 
         showNotification('Failed to start monitoring', 'error'); 
         return false; 
     } 
 } 
 
 // Stop monitoring for a specific device 
 async function stopDeviceMonitoring(deviceId) { 
     try { 
         const response = await fetch(`/api/devices/${deviceId}/stop`, { 
             method: 'POST' 
         }); 
         const data = await response.json(); 
         
         if (response.ok) { 
             showNotification(`Monitoring stopped for ${deviceId}`, 'success'); 
             return true; 
         } 
         return false; 
     } catch (error) { 
         console.error('Stop monitoring error:', error); 
         showNotification('Failed to stop monitoring', 'error'); 
         return false; 
     } 
 } 
 
 // Get device-specific status 
 async function getDeviceStatus(deviceId) { 
     try { 
         const response = await fetch(`/api/devices/${deviceId}/status`); 
         const data = await response.json(); 
         return data; 
     } catch (error) { 
         console.error('Get device status error:', error); 
         return null; 
     } 
 } 
 
 // Set thresholds for a specific device 
 async function setDeviceThresholds(deviceId, thresholds) { 
     try { 
         const response = await fetch(`/api/devices/${deviceId}/thresholds`, { 
             method: 'POST', 
             headers: { 
                 'Content-Type': 'application/json' 
             }, 
             body: JSON.stringify(thresholds) 
         }); 
         const data = await response.json(); 
         
         if (response.ok) { 
             showNotification(`Thresholds updated for ${deviceId}`, 'success'); 
             return true; 
         } 
         return false; 
     } catch (error) { 
         console.error('Set thresholds error:', error); 
         showNotification('Failed to set thresholds', 'error'); 
         return false; 
     } 
 } 
 
 // Manual control for a specific device 
 async function manualControlDevice(deviceId, device, state) { 
     try { 
         const response = await fetch(`/api/devices/${deviceId}/control/${device}`, { 
             method: 'POST', 
             headers: { 
                 'Content-Type': 'application/json' 
             }, 
             body: JSON.stringify({ state: state }) 
         }); 
         const data = await response.json(); 
         
         if (response.ok) { 
             const stateText = state === true ? 'ON' : state === false ? 'OFF' : 'AUTO'; 
             showNotification(`${device} set to ${stateText} for ${deviceId}`, 'success'); 
             return true; 
         } 
         return false; 
     } catch (error) { 
         console.error('Manual control error:', error); 
         showNotification('Failed to control device', 'error'); 
         return false; 
     } 
 } 
 
 // Get device history 
 async function getDeviceHistory(deviceId, limit = 10) { 
     try { 
         const response = await fetch(`/api/devices/${deviceId}/history?limit=${limit}`); 
         const data = await response.json(); 
         return data; 
     } catch (error) { 
         console.error('Get device history error:', error); 
         return []; 
     } 
 } 
 
 // Get device events 
 async function getDeviceEvents(deviceId, limit = 50) { 
     try { 
         const response = await fetch(`/api/devices/${deviceId}/events?limit=${limit}`); 
         const data = await response.json(); 
         return data; 
     } catch (error) { 
         console.error('Get device events error:', error); 
         return []; 
     } 
 } 
 
 // Clear device buffer 
 async function clearDeviceBuffer(deviceId) { 
     try { 
         const response = await fetch(`/api/devices/${deviceId}/buffer/clear`, { 
             method: 'POST' 
         }); 
         const data = await response.json(); 
         
         if (response.ok) { 
             showNotification(`Buffer cleared for ${deviceId}`, 'success'); 
             return true; 
         } 
         return false; 
     } catch (error) { 
         console.error('Clear buffer error:', error); 
         showNotification('Failed to clear buffer', 'error'); 
         return false; 
     } 
 } 

let updateInterval = null;
let eventCheckInterval = null;
let chart = null;
let isConnected = false;
let isMonitoring = false;
let connectionInfo = {
    host: null,
    port: null,
    connected: false
};

// Multi-device variables
let devices = [];
let activeDeviceId = null;
let currentDeviceInfo = null;

// Network discovery variables
let discoveredDevices = [];
let isScanning = false;

// Store last known threshold values to avoid overwriting user changes
let lastThresholds = {
    temp_threshold: null,
    buzzer_temp_threshold: null,
    humidity_threshold: null,
    buzzer_humidity_threshold: null
};
// Track if user recently modified thresholds (within last 3 seconds)
let recentUserChanges = {
    temp_threshold: false,
    buzzer_temp_threshold: false,
    humidity_threshold: false,
    buzzer_humidity_threshold: false
};

// Mode cycle mapping
const MODE_CYCLE = {
    'auto': 'manual_on',
    'manual_on': 'manual_off',
    'manual_off': 'auto'
};

const MODE_DISPLAY = {
    'auto': { text: 'AUTO', class: 'auto' },
    'manual_on': { text: 'MANUAL ON', class: 'manual-on' },
    'manual_off': { text: 'MANUAL OFF', class: 'manual-off' }
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ DOMContentLoaded - Starting app initialization...');
    
    try {
        initializeChart();
        console.log('✅ Chart initialized');
        
        setupEventListeners();
        console.log('✅ Event listeners setup');
        
        checkBackendStatus();
        console.log('✅ Backend status check started');
        
        // Start a global background poll that always runs
        // This keeps multiple browser windows in sync even if no device is active yet
        startGlobalPolling();
        
        loadDevices(true); // Initial load will auto-select active device
        console.log('✅ Load devices called (initial)');
        
        getNetworkInfo();
        console.log('✅ Network info requested');
        
        console.log('🎉 App initialization complete!');
    } catch (error) {
        console.error('❌ Initialization error:', error);
        alert('App initialization failed! Check console for details.');
    }
});

let globalPollInterval = null;

// Always run this to keep browsers in sync
function startGlobalPolling() {
    if (globalPollInterval) clearInterval(globalPollInterval);
    globalPollInterval = setInterval(() => {
        // Sync device list and active device selection across browsers
        loadDevices();
        
        // If a device is selected but monitoring isn't running, we still need to sync its status
        if (activeDeviceId && !isMonitoring) {
            updateSystemStatus();
        }
    }, 2000); // Check every 2 seconds for global state changes
}

// Initialize Chart.js
function initializeChart() {
    const ctx = document.getElementById('sensorChart').getContext('2d');
    chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Temperature (°C)',
                    data: [],
                    borderColor: '#f56565',
                    backgroundColor: 'rgba(245, 101, 101, 0.1)',
                    tension: 0.4,
                    fill: true,
                    yAxisID: 'y-temperature'
                },
                {
                    label: 'Humidity (%)',
                    data: [],
                    borderColor: '#4299e1',
                    backgroundColor: 'rgba(66, 153, 225, 0.1)',
                    tension: 0.4,
                    fill: true,
                    yAxisID: 'y-humidity'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    labels: {
                        color: '#fff'
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#fff',
                    bodyColor: '#fff'
                }
            },
            scales: {
                'y-temperature': {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: {
                        display: true,
                        text: 'Temperature (°C)',
                        color: '#f56565'
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: '#f56565'
                    }
                },
                'y-humidity': {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: {
                        display: true,
                        text: 'Humidity (%)',
                        color: '#4299e1'
                    },
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: '#4299e1'
                    },
                    min: 0,
                    max: 100
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: '#fff',
                        maxRotation: 45,
                        minRotation: 45
                    }
                }
            }
        }
    });
}

// Setup event listeners
function setupEventListeners() {
    console.log('🔧 Setting up event listeners...');
    
    try {
        // Connection buttons
        const connectBtn = document.getElementById('connectBtn');
        if (connectBtn) {
            connectBtn.addEventListener('click', connectToESP);
            console.log('✅ connectBtn listener added');
        } else {
            console.warn('⚠️ connectBtn not found');
        }
        
        const disconnectBtn = document.getElementById('disconnectBtn');
        if (disconnectBtn) {
            disconnectBtn.addEventListener('click', disconnectFromESP);
            console.log('✅ disconnectBtn listener added');
        } else {
            console.warn('⚠️ disconnectBtn not found');
        }
        
        const testConnectionBtn = document.getElementById('testConnectionBtn');
        if (testConnectionBtn) {
            testConnectionBtn.addEventListener('click', testConnection);
            console.log('✅ testConnectionBtn listener added');
        } else {
            console.warn('⚠️ testConnectionBtn not found');
        }
        
        // Network discovery listeners
        const quickScanBtn = document.getElementById('quickScanBtn');
        if (quickScanBtn) {
            quickScanBtn.addEventListener('click', () => {
                console.log('🔘 Quick Scan button clicked!');
                scanNetwork('quick');
            });
            console.log('✅ quickScanBtn listener added');
        } else {
            console.warn('⚠️ quickScanBtn not found - this is expected if using new device panel');
        }
        
        const refreshDevicesBtn = document.getElementById('refreshDevicesBtn');
        if (refreshDevicesBtn) {
            refreshDevicesBtn.addEventListener('click', refreshDeviceList);
            console.log('✅ refreshDevicesBtn listener added');
        } else {
            console.warn('⚠️ refreshDevicesBtn not found');
        }
        
        const deviceSelect = document.getElementById('deviceSelect');
        if (deviceSelect) {
            deviceSelect.addEventListener('change', handleDeviceSelect);
            console.log('✅ deviceSelect listener added');
        } else {
            console.warn('⚠️ deviceSelect not found');
        }
        
        // System control buttons
        const startSystem = document.getElementById('startSystem');
        if (startSystem) {
            startSystem.addEventListener('click', startMonitoring);
            console.log('✅ startSystem listener added');
        } else {
            console.warn('⚠️ startSystem not found');
        }
        
        const stopSystem = document.getElementById('stopSystem');
        if (stopSystem) {
            stopSystem.addEventListener('click', stopMonitoring);
            console.log('✅ stopSystem listener added');
        } else {
            console.warn('⚠️ stopSystem not found');
        }
        
        const disconnectDeviceBtn = document.getElementById('disconnectDeviceBtn');
        if (disconnectDeviceBtn) {
            disconnectDeviceBtn.addEventListener('click', disconnectActiveDevice);
            console.log('✅ disconnectDeviceBtn listener added');
        } else {
            console.warn('⚠️ disconnectDeviceBtn not found');
        }
        
        // Cyclic control buttons
        const tempLEDCycle = document.getElementById('tempLEDCycle');
        if (tempLEDCycle) {
            tempLEDCycle.addEventListener('click', () => cycleDeviceMode('temp_led'));
            console.log('✅ tempLEDCycle listener added');
        } else {
            console.warn('⚠️ tempLEDCycle not found');
        }
        
        const humidityLEDCycle = document.getElementById('humidityLEDCycle');
        if (humidityLEDCycle) {
            humidityLEDCycle.addEventListener('click', () => cycleDeviceMode('humidity_led'));
            console.log('✅ humidityLEDCycle listener added');
        } else {
            console.warn('⚠️ humidityLEDCycle not found');
        }
        
        const buzzerCycle = document.getElementById('buzzerCycle');
        if (buzzerCycle) {
            buzzerCycle.addEventListener('click', () => cycleDeviceMode('buzzer'));
            console.log('✅ buzzerCycle listener added');
        } else {
            console.warn('⚠️ buzzerCycle not found');
        }
        
        // Threshold sliders
        setupSliderSync('tempThresholdInput', 'tempThresholdSlider', 'temp_threshold');
        setupSliderSync('buzzerTempThresholdInput', 'buzzerTempThresholdSlider', 'buzzer_temp_threshold');
        setupSliderSync('humidityThresholdInput', 'humidityThresholdSlider', 'humidity_threshold');
        setupSliderSync('buzzerHumidityThresholdInput', 'buzzerHumidityThresholdSlider', 'buzzer_humidity_threshold');
        console.log('✅ Slider sync setup complete');
        
        // Save thresholds button
        const saveThresholdsBtn = document.getElementById('saveThresholds');
        if (saveThresholdsBtn) {
            saveThresholdsBtn.addEventListener('click', saveThresholds);
            console.log('✅ saveThresholds listener added');
        } else {
            console.warn('⚠️ saveThresholds button not found');
        }
        
        // Buffer control
        const clearBuffer = document.getElementById('clearBuffer');
        if (clearBuffer) {
            clearBuffer.addEventListener('click', clearBuffer);
            console.log('✅ clearBuffer listener added');
        } else {
            console.warn('⚠️ clearBuffer not found');
        }
        
        // Events refresh
        const refreshEvents = document.getElementById('refreshEvents');
        if (refreshEvents) {
            refreshEvents.addEventListener('click', refreshEvents);
            console.log('✅ refreshEvents listener added');
        } else {
            console.warn('⚠️ refreshEvents not found');
        }
        
        // Manual add device
        const addDeviceBtn = document.getElementById('addDeviceBtn');
        if (addDeviceBtn) {
            addDeviceBtn.addEventListener('click', addManualDevice);
            console.log('✅ addDeviceBtn listener added');
        } else {
            console.warn('⚠️ addDeviceBtn not found');
        }
        
        // Toggle disconnected devices visibility
        const toggleDisconnectedBtn = document.getElementById('toggleDisconnectedBtn');
        if (toggleDisconnectedBtn) {
            toggleDisconnectedBtn.addEventListener('click', toggleShowDisconnected);
            console.log('✅ toggleDisconnectedBtn listener added');
        } else {
            console.warn('⚠️ toggleDisconnectedBtn not found - may need to add to HTML');
        }
        
        console.log('🎉 All event listeners setup complete!');
    } catch (error) {
        console.error('❌ Error setting up event listeners:', error);
    }
}

// Load devices from backend
async function loadDevices(isInitialLoad = false) {
    console.log('📥 Loading devices from backend...');
    try {
        // Check if user wants to see disconnected devices
        const showDisconnected = localStorage.getItem('showDisconnected') === 'true';
        const url = `/api/devices${showDisconnected ? '?connected_only=false' : '?connected_only=true'}`;
        
        const response = await fetch(url);
        const data = await response.json();
        console.log('📋 Received devices:', data);
        devices = data;
        
        // Get active device from backend
        const activeResponse = await fetch('/api/devices/active');
        const activeData = await activeResponse.json();
        const serverActiveId = activeData.active_device;
        
        console.log('🎯 Active device on server:', serverActiveId);
        
        // Sync active device across browsers
        // If server says Device A is active, but we show Device B (or nothing), switch to Device A
        if (serverActiveId && serverActiveId !== activeDeviceId) {
            console.log(`🔄 Syncing: Switching from ${activeDeviceId} to ${serverActiveId}`);
            await selectDevice(serverActiveId, true); // true = silent (no notification)
        } else if (!serverActiveId && activeDeviceId) {
            // Server has no active device, but we do - clear our local state
            console.log(`�️ Syncing: Clearing active device as server has none`);
            activeDeviceId = null;
            document.getElementById('activeDeviceText').textContent = 'None Selected';
            document.getElementById('systemPanel').style.display = 'none';
            document.getElementById('dashboard').style.display = 'none';
            document.getElementById('noDeviceMessage').style.display = 'block';
        }
        
        renderDeviceGrid();
        updateShowDisconnectedToggle();
        console.log(`✅ Device grid rendered with ${devices.length} devices`);
    } catch (error) {
        console.error('❌ Error loading devices:', error);
    }
}

// Render device grid
function renderDeviceGrid() {
    console.log('🎨 Rendering device grid...', { devices, activeDeviceId });
    
    const showDisconnected = localStorage.getItem('showDisconnected') === 'true';
    
    // Check if any devices are disconnected
    const disconnectedCount = devices.filter(d => !d.connected).length;
    if (disconnectedCount > 0 && showDisconnected) {
        console.warn(`⚠️ ${disconnectedCount} device(s) not connected (currently visible)!`);
    } else if (disconnectedCount > 0 && !showDisconnected) {
        console.warn(`⚠️ ${disconnectedCount} device(s) not connected (hidden - toggle to show)`);
    }
    
    const grid = document.getElementById('deviceGrid');
    if (!grid) {
        console.error('❌ deviceGrid element not found!');
        return;
    }
    
    if (!devices || devices.length === 0) {
        const message = showDisconnected 
            ? '🔍 No devices found. Click "Quick Scan" to discover ESP32 devices.'
            : '🔍 No connected devices found. Disconnected devices are hidden.';
        grid.innerHTML = `<div class="device-card loading"><p>${message}</p></div>`;
        console.log('✅ No devices message displayed');
        return;
    }
    
    console.log(`✅ Rendering ${devices.length} device(s) in grid (${showDisconnected ? 'showing' : 'hiding'} disconnected)`);
    
    let html = '';
    devices.forEach(device => {
        const isSelected = (activeDeviceId === device.id);
        const statusClass = device.connected ? 'connected' : 'disconnected';
        const statusText = device.connected ? 'Connected' : 'NOT CONNECTED';
            
        console.log(`📋 Rendering device: ${device.id} (${device.room}), connected: ${device.connected}, temp: ${device.temperature}, humidity: ${device.humidity}`);
            
        // Show warning message if not connected
        const connectionWarning = !device.connected ? `
            <div style="grid-column: 1 / -1; background: rgba(245, 101, 101, 0.2); border: 1px solid #f56565; padding: 8px; border-radius: 5px; margin-top: 10px; font-size: 12px; color: #f56565;">
                ⚠️ Device not available - Click "Connect" button first
            </div>
        ` : '';
        
        // Prevent click selection for disconnected devices
        const clickHandler = device.connected ? `onclick="selectDevice('${device.id}')"` : '';
        const cursorStyle = device.connected ? 'cursor: pointer;' : 'cursor: not-allowed; opacity: 0.7;';
        
        if (!device.connected) {
            console.log(`🚫 Device ${device.id} - click handler disabled, cursor: not-allowed`);
        }
            
        html += `
            <div class="device-card ${statusClass} ${isSelected ? 'selected' : ''}" ${clickHandler} style="${cursorStyle}">
                <div class="device-card-header">
                    <span class="device-room">🏠 ${device.room || device.name}</span>
                    <span class="device-status-badge ${statusClass}" style="background: ${device.connected ? '#48bb78' : '#f56565'};">${statusText}</span>
                </div>
                <div class="device-ip">📍 ${device.ip}:${device.port}</div>
                <div class="device-sensors">
                    <div class="device-sensor">
                        <span class="sensor-label">Temperature</span>
                        <span class="sensor-value" style="${!device.connected ? 'color: #f56565;' : ''}" title="${device.connected ? '' : '⚠️ Device not available - Click Connect button'}">${device.connected && device.temperature !== null ? device.temperature.toFixed(1) + '°C' : '❌ --'}</span>
                    </div>
                    <div class="device-sensor">
                        <span class="sensor-label">Humidity</span>
                        <span class="sensor-value" style="${!device.connected ? 'color: #f56565;' : ''}" title="${device.connected ? '' : '⚠️ Device not available - Click Connect button'}">${device.connected && device.humidity !== null ? device.humidity.toFixed(1) + '%' : '❌ --'}</span>
                    </div>
                </div>
                ${connectionWarning}
                <div class="device-actions">
                    <button class="btn btn-small btn-primary" onclick="event.stopPropagation(); connectDevice('${device.id}')" ${device.connected ? 'disabled' : ''}>
                        ${device.connected ? '✅ Connected' : '🔌 Connect'}
                    </button>
                    <button class="btn btn-small btn-danger" onclick="event.stopPropagation(); removeDevice('${device.id}')">
                        Remove
                    </button>
                </div>
            </div>
        `;
    });
    
    grid.innerHTML = html;
}

// Select a device
async function selectDevice(deviceId, silent = false) {
    console.log(`👆 Select device called for: ${deviceId}, silent: ${silent}`);
    
    const device = devices.find(d => d.id === deviceId);
    if (!device) {
        console.error(`❌ Device ${deviceId} not found in devices list`, devices);
        return;
    }
    
    console.log(`🔍 Device ${deviceId} connection status:`, device.connected);
    
    // If device is not connected, show error and remove from active device
    if (!device.connected) {
        console.error(`❌ Device ${deviceId} not connected - blocking selection`);
        if (!silent) {
            showNotification(`❌ Device "${device.room || deviceId}" is not available. Please connect it first.`, 'error');
        }
        
        // Remove from active device if it was set
        if (activeDeviceId === deviceId) {
            console.log(`🗑️ Removing disconnected device ${deviceId} from active list`);
            activeDeviceId = null;
            document.getElementById('activeDeviceText').textContent = 'None Selected';
            document.getElementById('systemPanel').style.display = 'none';
            document.getElementById('dashboard').style.display = 'none';
            document.getElementById('noDeviceMessage').style.display = 'block';
        }
        return;
    }
    
    console.log(`✅ Device ${deviceId} is connected - proceeding with selection`);
    
    try {
        const response = await fetch(`/api/devices/${deviceId}/active`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            activeDeviceId = deviceId;
            renderDeviceGrid();
            
            // Update UI
            document.getElementById('activeDeviceText').textContent = deviceId;
            document.getElementById('activeRoomName').textContent = device.room || deviceId;
            
            // Load device info
            await loadDeviceInfo(deviceId);
            
            // Show system panels
            document.getElementById('systemPanel').style.display = 'block';
            document.getElementById('dashboard').style.display = 'grid';
            document.getElementById('noDeviceMessage').style.display = 'none';
            
            if (!silent) {
                showNotification(`✅ Selected ${device.room || deviceId}`, 'success');
            }
            
            // Set monitoring state for the selected device
            isMonitoring = device.monitoring_active || false;
            
            // Enable/disable start/stop monitoring buttons based on current state
            const startSystemBtn = document.getElementById('startSystem');
            const stopSystemBtn = document.getElementById('stopSystem');
            const systemStatusBadge = document.getElementById('systemStatusBadge');
            
            if (device.connected) {
                if (isMonitoring) {
                    if (startSystemBtn) startSystemBtn.disabled = true;
                    if (stopSystemBtn) stopSystemBtn.disabled = false;
                    if (systemStatusBadge) systemStatusBadge.innerHTML = '<span class="badge running">System Running</span>';
                    console.log(`✅ Monitoring is already active for ${deviceId}.`);
                    
                    // Start periodic updates automatically if monitoring is active
                    startPeriodicUpdates();
                } else {
                    if (startSystemBtn) startSystemBtn.disabled = false;
                    if (stopSystemBtn) stopSystemBtn.disabled = true;
                    if (systemStatusBadge) systemStatusBadge.innerHTML = '<span class="badge idle">System Idle</span>';
                    console.log(`✅ Device connected. Click "Start Monitoring" to begin.`);
                }
            }
        } else {
            // Backend returned error (e.g., device not connected)
            console.error(`❌ Failed to select device: ${data.message}`);
            if (!silent) {
                showNotification(data.message || `Failed to select ${device.room || deviceId}`, 'error');
            }
            
            // Clear active device if set
            if (activeDeviceId === deviceId) {
                activeDeviceId = null;
                document.getElementById('activeDeviceText').textContent = 'None Selected';
                document.getElementById('systemPanel').style.display = 'none';
                document.getElementById('dashboard').style.display = 'none';
                document.getElementById('noDeviceMessage').style.display = 'block';
            }
        }
    } catch (error) {
        console.error('Error selecting device:', error);
        if (!silent) {
            showNotification('Failed to select device', 'error');
        }
    }
}

// Connect to a specific device
async function connectDevice(deviceId) {
    try {
        const response = await fetch(`/api/devices/${deviceId}/connect`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showNotification(data.message, 'success');
            await loadDevices(); // Refresh device list
            
            // Only auto-select if connection succeeds
            const device = devices.find(d => d.id === deviceId) || 
                          (await fetch('/api/devices').then(r => r.json())).find(d => d.id === deviceId);
            
            if (device && device.connected) {
                await selectDevice(deviceId); // Auto-select after connect
            }
            
            // Update connection status
            isConnected = true;
            const connectBtnEl = document.getElementById('connectBtn');
            if (connectBtnEl) connectBtnEl.disabled = true;
            const disconnectBtnEl = document.getElementById('disconnectBtn');
            if (disconnectBtnEl) disconnectBtnEl.disabled = false;
            const testConnectionBtnEl = document.getElementById('testConnectionBtn');
            if (testConnectionBtnEl) testConnectionBtnEl.disabled = false;
            const esp32IndicatorEl = document.getElementById('esp32Indicator');
            if (esp32IndicatorEl) esp32IndicatorEl.classList.add('connected');
            const esp32TextEl = document.getElementById('esp32Text');
            if (esp32TextEl) esp32TextEl.textContent = 'Connected';
            const connectionInfoEl = document.getElementById('connectionInfo');
            if (connectionInfoEl) connectionInfoEl.innerHTML = `<span class="info-label">Connected to ${deviceId}</span>`;
            const disconnectDeviceBtnEl = document.getElementById('disconnectDeviceBtn');
            if (disconnectDeviceBtnEl) disconnectDeviceBtnEl.disabled = false;
            const startSystemEl = document.getElementById('startSystem');
            if (startSystemEl) startSystemEl.disabled = false;
            
            console.log(`✅ Connected to ${deviceId}. Click "Start Monitoring" to begin receiving sensor data.`);
        } else {
            showNotification(`❌ ${data.message}`, 'error');
            // Remove from active device if connection failed
            if (activeDeviceId === deviceId) {
                activeDeviceId = null;
                document.getElementById('activeDeviceText').textContent = 'None Selected';
            }
        }
    } catch (error) {
        console.error('Error connecting to device:', error);
        showNotification('Failed to connect to device', 'error');
        // Remove from active device if connection failed
        if (activeDeviceId === deviceId) {
            activeDeviceId = null;
            document.getElementById('activeDeviceText').textContent = 'None Selected';
        }
    }
}

// Disconnect active device
async function disconnectActiveDevice() {
    if (!activeDeviceId) return;
    
    try {
        const response = await fetch(`/api/devices/${activeDeviceId}/disconnect`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showNotification(data.message, 'success');
            
            // Stop monitoring if running
            if (isMonitoring) {
                await stopMonitoring();
            }
            
            isConnected = false;
            isMonitoring = false;
            activeDeviceId = null;
            
            await loadDevices();
            
            // Hide system panels
            const systemPanelEl = document.getElementById('systemPanel');
            if (systemPanelEl) systemPanelEl.style.display = 'none';
            const dashboardEl = document.getElementById('dashboard');
            if (dashboardEl) dashboardEl.style.display = 'none';
            const noDeviceMsgEl = document.getElementById('noDeviceMessage');
            if (noDeviceMsgEl) noDeviceMsgEl.style.display = 'block';
            const activeDeviceTextEl = document.getElementById('activeDeviceText');
            if (activeDeviceTextEl) activeDeviceTextEl.textContent = 'None Selected';
            const esp32IndicatorEl = document.getElementById('esp32Indicator');
            if (esp32IndicatorEl) esp32IndicatorEl.classList.remove('connected');
            const esp32TextEl = document.getElementById('esp32Text');
            if (esp32TextEl) esp32TextEl.textContent = 'Disconnected';
            const connectionInfoEl = document.getElementById('connectionInfo');
            if (connectionInfoEl) connectionInfoEl.innerHTML = '<span class="info-label">Not Connected</span>';
            
            // Stop periodic updates
            stopPeriodicUpdates();
        }
    } catch (error) {
        console.error('Error disconnecting device:', error);
        showNotification('Failed to disconnect', 'error');
    }
}

// Toggle show/hide disconnected devices
function toggleShowDisconnected() {
    const current = localStorage.getItem('showDisconnected') === 'true';
    localStorage.setItem('showDisconnected', !current);
    updateShowDisconnectedToggle();
    loadDevices(); // Reload devices with new filter
}

function updateShowDisconnectedToggle() {
    const showDisconnected = localStorage.getItem('showDisconnected') === 'true';
    const toggleBtn = document.getElementById('toggleDisconnectedBtn');
    
    if (toggleBtn) {
        toggleBtn.textContent = showDisconnected ? '🙈 Hide Disconnected' : '👁️ Show Disconnected';
        toggleBtn.classList.toggle('active', showDisconnected);
        
        // Update tooltip
        const disconnectedCount = devices.filter(d => !d.connected).length;
        toggleBtn.title = showDisconnected 
            ? 'Click to hide disconnected devices' 
            : `Click to show ${disconnectedCount} disconnected device(s)`;
    }
}

// Remove a device
let isRemovingDevice = false;

async function removeDevice(deviceId) {
    if (isRemovingDevice) {
        console.log('⚠️ Already removing a device, ignoring duplicate call');
        return;
    }
    
    if (!confirm(`Are you sure you want to remove device ${deviceId}?`)) return;
    
    isRemovingDevice = true;
    console.log(`🗑️ Removing device: ${deviceId}`);
    
    try {
        const response = await fetch(`/api/devices/${deviceId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        console.log(`📋 Remove response:`, data);
        
        if (response.ok) {
            showNotification(`✅ ${data.message}`, 'success');
            await loadDevices();
            
            if (activeDeviceId === deviceId) {
                activeDeviceId = null;
                isConnected = false;
                isMonitoring = false;
                const systemPanelEl = document.getElementById('systemPanel');
                if (systemPanelEl) systemPanelEl.style.display = 'none';
                const dashboardEl = document.getElementById('dashboard');
                if (dashboardEl) dashboardEl.style.display = 'none';
                const noDeviceMsgEl = document.getElementById('noDeviceMessage');
                if (noDeviceMsgEl) noDeviceMsgEl.style.display = 'block';
                const activeDeviceTextEl = document.getElementById('activeDeviceText');
                if (activeDeviceTextEl) activeDeviceTextEl.textContent = 'None Selected';
                const esp32IndicatorEl = document.getElementById('esp32Indicator');
                if (esp32IndicatorEl) esp32IndicatorEl.classList.remove('connected');
                const esp32TextEl = document.getElementById('esp32Text');
                if (esp32TextEl) esp32TextEl.textContent = 'Disconnected';
                stopPeriodicUpdates();
            }
        } else {
            showNotification(`❌ ${data.message}`, 'error');
        }
    } catch (error) {
        console.error('Error removing device:', error);
        showNotification('❌ Failed to remove device', 'error');
    } finally {
        isRemovingDevice = false;
    }
}

// Add manual device
async function addManualDevice() {
    const room = document.getElementById('manualRoomName').value.trim();
    const ip = document.getElementById('manualIP').value.trim();
    const port = parseInt(document.getElementById('manualPort').value);
    
    if (!room || !ip) {
        showNotification('Please enter room name and IP address', 'error');
        return;
    }
    
    const deviceId = room.toLowerCase().replace(/\s+/g, '_');
    
    try {
        const response = await fetch('/api/devices', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                device_id: deviceId,
                ip: ip,
                port: port,
                room: room,
                name: room
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showNotification(data.message, 'success');
            await loadDevices();
            
            // Clear form
            document.getElementById('manualRoomName').value = '';
            document.getElementById('manualIP').value = '';
            document.getElementById('manualPort').value = '502';
            
            // Auto-connect to the new device
            await connectDevice(deviceId);
        } else {
            showNotification(data.message, 'error');
        }
    } catch (error) {
        console.error('Error adding device:', error);
        showNotification('Failed to add device', 'error');
    }
}

// Load device info
async function loadDeviceInfo(deviceId) {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        if (data.device_id) {
            document.getElementById('infoRoom').textContent = data.device_name || data.device_id;
            document.getElementById('infoDeviceId').textContent = data.device_id;
            document.getElementById('infoIP').textContent = `${data.modbus?.host || '--'}:${data.modbus?.port || '--'}`;
            document.getElementById('infoStatus').textContent = data.modbus?.connected ? 'Connected' : 'Disconnected';
            
            // Also update the full dashboard and buttons
            updateUI(data);
        }
    } catch (error) {
        console.error('Error loading device info:', error);
    }
}

// Setup slider and input synchronization
function setupSliderSync(inputId, sliderId, thresholdKey) {
    const input = document.getElementById(inputId);
    const slider = document.getElementById(sliderId);
    
    console.log(`Setting up slider sync: ${inputId} <-> ${sliderId}`, { input, slider });
    
    if (input && slider) {
        input.addEventListener('input', function() {
            slider.value = this.value;
            if (thresholdKey) {
                recentUserChanges[thresholdKey] = true;
                setTimeout(() => {
                    recentUserChanges[thresholdKey] = false;
                }, 3000);
            }
        });
        
        slider.addEventListener('input', function() {
            input.value = this.value;
            if (thresholdKey) {
                recentUserChanges[thresholdKey] = true;
                setTimeout(() => {
                    recentUserChanges[thresholdKey] = false;
                }, 3000);
            }
        });
    }
}

// Cycle device mode
async function cycleDeviceMode(device) {
    if (!isConnected) {
        showNotification('Please connect to ESP32 first', 'error');
        return;
    }
    
    if (!isMonitoring) {
        showNotification('Please start monitoring first', 'warning');
        return;
    }
    
    try {
        let currentMode = 'auto';
        if (device === 'temp_led') {
            currentMode = getModeFromBadge('tempLEDMode');
        } else if (device === 'humidity_led') {
            currentMode = getModeFromBadge('humidityLEDMode');
        } else if (device === 'buzzer') {
            currentMode = getModeFromBadge('buzzerMode');
        }
        
        const nextMode = MODE_CYCLE[currentMode];
        let state = null;
        if (nextMode === 'manual_on') state = true;
        else if (nextMode === 'manual_off') state = false;
        
        const response = await fetch(`/api/control/${device}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ state: state })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            updateDeviceModeUI(device, nextMode);
            showNotification(`${getDeviceName(device)} switched to ${MODE_DISPLAY[nextMode].text}`, 'success');
            
            const btn = document.getElementById(`${device.replace('_', '')}Cycle`);
            if (btn) {
                btn.classList.add('mode-changed');
                setTimeout(() => btn.classList.remove('mode-changed'), 300);
            }
        }
    } catch (error) {
        console.error('Cycle mode error:', error);
        showNotification('Failed to change mode', 'error');
    }
}

function getModeFromBadge(elementId) {
    const badge = document.getElementById(elementId);
    if (!badge) return 'auto';
    if (badge.classList.contains('auto')) return 'auto';
    if (badge.classList.contains('manual-on')) return 'manual_on';
    if (badge.classList.contains('manual-off')) return 'manual_off';
    return 'auto';
}

function updateDeviceModeUI(device, mode) {
    let badgeId;
    if (device === 'temp_led') badgeId = 'tempLEDMode';
    else if (device === 'humidity_led') badgeId = 'humidityLEDMode';
    else if (device === 'buzzer') badgeId = 'buzzerMode';
    
    const badge = document.getElementById(badgeId);
    if (badge) {
        badge.textContent = MODE_DISPLAY[mode].text;
        badge.className = `mode-badge ${MODE_DISPLAY[mode].class}`;
    }
    updateGlobalMode();
}

function getDeviceName(device) {
    const names = {
        'temp_led': 'Temperature LED',
        'humidity_led': 'Humidity LED',
        'buzzer': 'Buzzer'
    };
    return names[device] || device;
}

// Check backend status
async function checkBackendStatus() {
    try {
        const response = await fetch('/api/ping');
        if (response.ok) {
            document.getElementById('backendIndicator').classList.add('connected');
            document.getElementById('backendText').textContent = 'Running';
        }
    } catch (error) {
        console.error('Backend not reachable:', error);
        showConnectionMessage('Backend server not reachable', 'error');
    }
}

// Get network info
async function getNetworkInfo() {
    try {
        const response = await fetch('/api/network/info');
        const data = await response.json();
        if (response.ok) {
            console.log('Network Info:', data);
        }
    } catch (error) {
        console.error('Network info error:', error);
    }
}

// Network scan function
async function scanNetwork(type = 'quick') {
    console.log('scanNetwork called, isScanning:', isScanning);
    
    if (isScanning) {
        console.log('Scan already in progress');
        showNotification('⚡ Quick scan is already in progress! Please wait for it to complete.', 'warning');
        return;
    }
    
    // Show scan started message
    console.log('Starting scan...');
    showNotification('⚡ Quick Scan Started! Scanning for ESP32 devices...', 'info');
    
    isScanning = true;
    const progressDiv = document.getElementById('scanProgress');
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');
    const progressPercent = document.getElementById('progressPercent');
    
    console.log('Progress elements:', { progressDiv, progressBar, progressText, progressPercent });
    
    if (progressDiv) {
        progressDiv.style.display = 'flex';
        if (progressBar) progressBar.style.width = '0%';
        if (progressText) progressText.textContent = 'Scanning network for ESP32 devices...';
        if (progressPercent) progressPercent.textContent = '0%';
        console.log('Progress bar displayed');
    }
    
    try {
        const response = await fetch('/api/network/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: type })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            discoveredDevices = data.devices;
            
            // Animate progress to 100%
            if (progressBar) progressBar.style.width = '100%';
            if (progressPercent) progressPercent.textContent = '100%';
            
            // Wait a moment to show completion
            await new Promise(resolve => setTimeout(resolve, 500));
            
            if (data.count > 0) {
                showNotification(`✅ Found ${data.count} ESP32 device(s)!`, 'success');
            } else {
                showNotification('⚠️ No ESP32 devices found. Check terminal for details.', 'warning');
            }
            
            await loadDevices(); // Refresh device list
        } else {
            showNotification(data.message || '❌ Scan failed', 'error');
        }
    } catch (error) {
        console.error('Scan error:', error);
        showNotification('❌ Network scan failed', 'error');
    } finally {
        isScanning = false;
        if (progressDiv) {
            // Hide progress after a delay
            setTimeout(() => {
                progressDiv.style.display = 'none';
            }, 1500);
        }
    }
}

// Update device dropdown (legacy, kept for compatibility)
function updateDeviceDropdown(devices) {
    const select = document.getElementById('deviceSelect');
    if (!select) return;
    
    while (select.options.length > 1) select.remove(1);
    
    const esp32Devices = devices.filter(d => d.device_type === 'ESP32' || d.is_esp32);
    const otherDevices = devices.filter(d => !(d.device_type === 'ESP32' || d.is_esp32));
    
    if (esp32Devices.length > 0) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = 'ESP32 Devices';
        esp32Devices.forEach(device => {
            const option = document.createElement('option');
            option.value = device.ip;
            option.textContent = `${device.ip} - ${device.hostname} (ESP32)`;
            optgroup.appendChild(option);
        });
        select.appendChild(optgroup);
    }
    
    if (otherDevices.length > 0) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = 'Other Devices';
        otherDevices.forEach(device => {
            const option = document.createElement('option');
            option.value = device.ip;
            option.textContent = `${device.ip} - ${device.hostname} (${device.device_type})`;
            optgroup.appendChild(option);
        });
        select.appendChild(optgroup);
    }
    
    const separator = document.createElement('option');
    separator.disabled = true;
    separator.textContent = '──────────';
    select.appendChild(separator);
    
    const manualOption = document.createElement('option');
    manualOption.value = 'manual';
    manualOption.textContent = '✏️ Enter manually...';
    select.appendChild(manualOption);
}

function handleDeviceSelect(event) {
    const value = event.target.value;
    const manualForm = document.getElementById('manualForm');
    if (value === 'manual') {
        manualForm.style.display = 'block';
    } else if (value) {
        manualForm.style.display = 'none';
        document.getElementById('espHost').value = value;
    } else {
        manualForm.style.display = 'none';
    }
}

function showDeviceList(devices) {
    const container = document.getElementById('devicesContainer');
    const deviceListDiv = document.getElementById('deviceList');
    if (!container || !deviceListDiv) return;
    
    if (devices.length === 0) {
        deviceListDiv.style.display = 'none';
        return;
    }
    
    deviceListDiv.style.display = 'block';
    let html = '';
    devices.forEach(device => {
        const typeClass = getDeviceTypeClass(device.device_type);
        html += `
            <div class="device-item" onclick="selectDeviceFromList('${device.ip}')">
                <div class="device-info">
                    <span class="device-ip">${device.ip}</span>
                    <span class="device-hostname">${device.hostname}</span>
                </div>
                <span class="device-type-badge ${typeClass}">${device.device_type}</span>
            </div>
        `;
    });
    container.innerHTML = html;
}

function getDeviceTypeClass(type) {
    switch(type) {
        case 'ESP32': return 'esp32';
        case 'Mobile': return 'mobile';
        case 'Computer': return 'computer';
        case 'Router': return 'router';
        default: return 'unknown';
    }
}

function selectDeviceFromList(ip) {
    const select = document.getElementById('deviceSelect');
    for (let i = 0; i < select.options.length; i++) {
        if (select.options[i].value === ip) {
            select.selectedIndex = i;
            handleDeviceSelect({ target: select });
            break;
        }
    }
}

async function refreshDeviceList() {
    try {
        const response = await fetch('/api/network/common');
        const data = await response.json();
        if (response.ok) {
            const commonSelect = document.getElementById('deviceSelect');
            if (commonSelect) {
                data.devices.forEach(device => {
                    const option = document.createElement('option');
                    option.value = device.ip;
                    option.textContent = `${device.ip} - ${device.hostname} (Common)`;
                    commonSelect.appendChild(option);
                });
            }
        }
    } catch (error) {
        console.error('Refresh error:', error);
    }
}

// Connect to ESP32 (legacy, kept for compatibility)
async function connectToESP() {
    const select = document.getElementById('deviceSelect');
    const selectedValue = select ? select.value : null;
    let host, port;
    
    if (selectedValue === 'manual' || !selectedValue) {
        host = document.getElementById('espHost').value.trim();
        port = parseInt(document.getElementById('espPort').value);
    } else {
        host = selectedValue;
        port = 502;
        const device = discoveredDevices.find(d => d.ip === host);
        if (device && device.port) port = device.port;
    }
    
    if (!host) {
        showConnectionMessage('Please enter or select ESP32 IP address', 'error');
        return;
    }
    
    showConnectionMessage('Connecting to ESP32...', 'info');
    
    try {
        const response = await fetch('/api/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ host: host, port: port })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showConnectionMessage(data.message, 'success');
            isConnected = true;
            document.getElementById('connectBtn').disabled = true;
            document.getElementById('disconnectBtn').disabled = false;
            document.getElementById('testConnectionBtn').disabled = false;
            document.getElementById('esp32Indicator').classList.add('connected');
            document.getElementById('esp32Text').textContent = 'Connected';
            document.getElementById('connectionInfo').innerHTML = `<span class="info-label">Connected to ${host}:${port}</span>`;
            document.getElementById('systemPanel').style.display = 'block';
            document.getElementById('dashboard').style.display = 'grid';
            document.getElementById('disconnectedMessage').style.display = 'none';
            
            await loadSystemStatus();
            await loadSensorHistory();
            await refreshEvents();
            startPeriodicUpdates();
        } else {
            showConnectionMessage(data.message, 'error');
        }
    } catch (error) {
        console.error('Connection error:', error);
        showConnectionMessage('Failed to connect to ESP32', 'error');
    }
}

async function disconnectFromESP() {
    try {
        if (isMonitoring) await stopMonitoring();
        
        const response = await fetch('/api/disconnect', { method: 'POST' });
        const data = await response.json();
        
        if (response.ok) {
            showConnectionMessage(data.message, 'success');
            isConnected = false;
            document.getElementById('connectBtn').disabled = false;
            document.getElementById('disconnectBtn').disabled = true;
            document.getElementById('testConnectionBtn').disabled = true;
            document.getElementById('esp32Indicator').classList.remove('connected');
            document.getElementById('esp32Text').textContent = 'Disconnected';
            document.getElementById('connectionInfo').innerHTML = '<span class="info-label">Not Connected</span>';
            document.getElementById('systemPanel').style.display = 'none';
            document.getElementById('dashboard').style.display = 'none';
            document.getElementById('disconnectedMessage').style.display = 'block';
            stopPeriodicUpdates();
        }
    } catch (error) {
        console.error('Disconnect error:', error);
        showConnectionMessage('Failed to disconnect', 'error');
    }
}

async function testConnection() {
    if (!isConnected) return;
    try {
        const response = await fetch('/api/connection/status');
        const data = await response.json();
        if (data.connected) {
            showConnectionMessage(`Connection to ${data.host}:${data.port} is active`, 'success');
        } else {
            showConnectionMessage('Connection test failed', 'error');
        }
    } catch (error) {
        showConnectionMessage('Connection test failed', 'error');
    }
}

async function startMonitoring() {
    if (!isConnected) {
        showNotification('Please connect to ESP32 first', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/system/start', { method: 'POST' });
        const data = await response.json();
        
        if (response.ok) {
            showNotification(data.message, 'success');
            isMonitoring = true;
            document.getElementById('startSystem').disabled = true;
            document.getElementById('stopSystem').disabled = false;
            document.getElementById('systemStatusBadge').innerHTML = '<span class="badge running">System Running</span>';
            await loadSystemStatus();
            await loadSensorHistory();
            startPeriodicUpdates();
        }
    } catch (error) {
        console.error('Start error:', error);
        showNotification('Failed to start system', 'error');
    }
}

async function stopMonitoring() {
    try {
        const response = await fetch('/api/system/stop', { method: 'POST' });
        const data = await response.json();
        
        if (response.ok) {
            showNotification(data.message, 'success');
            isMonitoring = false;
            document.getElementById('startSystem').disabled = false;
            document.getElementById('stopSystem').disabled = true;
            document.getElementById('systemStatusBadge').innerHTML = '<span class="badge idle">System Idle</span>';
            stopPeriodicUpdates();
        }
    } catch (error) {
        console.error('Stop error:', error);
        showNotification('Failed to stop system', 'error');
    }
}

function startPeriodicUpdates() {
    if (updateInterval) clearInterval(updateInterval);
    updateInterval = setInterval(() => {
        // High frequency sensor data and status updates
        updateSystemStatus();
        loadSensorHistory();
    }, 1000); // 1 second for live monitoring
    
    if (eventCheckInterval) clearInterval(eventCheckInterval);
    eventCheckInterval = setInterval(refreshEvents, 2000); 
}

function stopPeriodicUpdates() {
    if (updateInterval) clearInterval(updateInterval);
    if (eventCheckInterval) clearInterval(eventCheckInterval);
}

async function loadSystemStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        updateUI(data);
    } catch (error) {
        console.error('Error loading status:', error);
    }
}

async function updateSystemStatus() {
    if (!isConnected) return;
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        updateUI(data);
    } catch (error) {
        console.error('Error updating status:', error);
    }
}

async function loadSensorHistory() {
    try {
        const response = await fetch('/api/sensors/history');
        const data = await response.json();
        updateChart(data);
        updateBufferInfo(data.length);
    } catch (error) {
        console.error('Error loading sensor history:', error);
    }
}

function updateUI(data) {
    window.currentData = data;
    
    // Check for connection loss
    const isESPConnected = data.modbus?.connected || (data.status === 'connected');
    const isMonActive = data.monitoring_active || false;
    
    // Update global states
    isConnected = isESPConnected;
    isMonitoring = isMonActive;
    
    // Update Connection Status in Device Info
    const infoStatus = document.getElementById('infoStatus');
    if (infoStatus) {
        infoStatus.textContent = isESPConnected ? 'Connected' : 'Disconnected';
        infoStatus.style.color = isESPConnected ? '#48bb78' : '#f56565';
    }
    
    // Handle Disconnected State
    if (!isESPConnected) {
        // Show notification if it was previously connected
        if (window.lastConnectionState === true) {
            showNotification(`❌ Connection lost with ESP32 (${data.device_id || 'Active Device'})`, 'error');
        }
        window.lastConnectionState = false;
        
        // Update values to indicate unavailability
        document.getElementById('tempValue').textContent = '--';
        document.getElementById('humidityValue').textContent = '--';
        document.getElementById('tempBadge').className = 'sensor-badge offline';
        document.getElementById('tempBadge').textContent = 'OFFLINE';
        document.getElementById('humidityBadge').className = 'sensor-badge offline';
        document.getElementById('humidityBadge').textContent = 'OFFLINE';
        
        // Disable control buttons
        const startBtn = document.getElementById('startSystem');
        const stopBtn = document.getElementById('stopSystem');
        if (startBtn) startBtn.disabled = true;
        if (stopBtn) stopBtn.disabled = true;
        
        const badge = document.getElementById('systemStatusBadge');
        if (badge) badge.innerHTML = '<span class="badge offline">ESP32 Not Available</span>';
        
        // Gray out device states
        document.getElementById('tempLEDState').className = 'device-state offline';
        document.getElementById('humidityLEDState').className = 'device-state offline';
        document.getElementById('buzzerState').className = 'device-state offline';
        
        updateGlobalMode();
        return; // Stop further UI updates for disconnected device
    }
    
    window.lastConnectionState = true;
    
    if (data.temperature !== null) {
        document.getElementById('tempValue').textContent = data.temperature.toFixed(1);
        const tempBadge = document.getElementById('tempBadge');
        if (data.temperature >= data.buzzer_temp_threshold) {
            tempBadge.className = 'sensor-badge critical';
            tempBadge.textContent = 'CRITICAL';
        } else if (data.temperature >= data.temp_threshold) {
            tempBadge.className = 'sensor-badge warning';
            tempBadge.textContent = 'WARNING';
        } else {
            tempBadge.className = 'sensor-badge normal';
            tempBadge.textContent = 'NORMAL';
        }
    }
    
    if (data.humidity !== null) {
        document.getElementById('humidityValue').textContent = data.humidity.toFixed(1);
        const humidityBadge = document.getElementById('humidityBadge');
        if (data.humidity >= data.buzzer_humidity_threshold) {
            humidityBadge.className = 'sensor-badge critical';
            humidityBadge.textContent = 'CRITICAL';
        } else if (data.humidity >= data.humidity_threshold) {
            humidityBadge.className = 'sensor-badge warning';
            humidityBadge.textContent = 'WARNING';
        } else {
            humidityBadge.className = 'sensor-badge normal';
            humidityBadge.textContent = 'NORMAL';
        }
    }
    
    updateBuzzerStatus(data.buzzer_state);
    updateDeviceLED('tempLED', data.temp_led_state);
    updateDeviceLED('humidityLED', data.humidity_led_state);
    updateDeviceLED('buzzerLED', data.buzzer_state);
    
    document.getElementById('tempLEDState').textContent = data.temp_led_state ? 'ON' : 'OFF';
    document.getElementById('tempLEDState').className = data.temp_led_state ? 'device-state on' : 'device-state off';
    document.getElementById('humidityLEDState').textContent = data.humidity_led_state ? 'ON' : 'OFF';
    document.getElementById('humidityLEDState').className = data.humidity_led_state ? 'device-state on' : 'device-state off';
    document.getElementById('buzzerState').textContent = data.buzzer_state ? 'ON' : 'OFF';
    document.getElementById('buzzerState').className = data.buzzer_state ? 'device-state on' : 'device-state off';
    
    document.getElementById('tempLEDCurrent').textContent = data.temp_led_state ? 'ON' : 'OFF';
    document.getElementById('humidityLEDCurrent').textContent = data.humidity_led_state ? 'ON' : 'OFF';
    document.getElementById('buzzerCurrent').textContent = data.buzzer_state ? 'ON' : 'OFF';
    
    updateModeBadge('tempLEDMode', data.manual_temp_led);
    updateModeBadge('humidityLEDMode', data.manual_humidity_led);
    updateModeBadge('buzzerMode', data.manual_buzzer);
    
    const tempThresholdInput = document.getElementById('tempThresholdInput');
    const buzzerTempThresholdInput = document.getElementById('buzzerTempThresholdInput');
    const humidityThresholdInput = document.getElementById('humidityThresholdInput');
    const buzzerHumidityThresholdInput = document.getElementById('buzzerHumidityThresholdInput');
    
    if (tempThresholdInput && parseFloat(tempThresholdInput.value) !== data.temp_threshold && 
        !tempThresholdInput.matches(':focus') && !recentUserChanges.temp_threshold) {
        tempThresholdInput.value = data.temp_threshold;
        document.getElementById('tempThresholdSlider').value = data.temp_threshold;
    }
    if (buzzerTempThresholdInput && parseFloat(buzzerTempThresholdInput.value) !== data.buzzer_temp_threshold && 
        !buzzerTempThresholdInput.matches(':focus') && !recentUserChanges.buzzer_temp_threshold) {
        buzzerTempThresholdInput.value = data.buzzer_temp_threshold;
        document.getElementById('buzzerTempThresholdSlider').value = data.buzzer_temp_threshold;
    }
    if (humidityThresholdInput && parseFloat(humidityThresholdInput.value) !== data.humidity_threshold && 
        !humidityThresholdInput.matches(':focus') && !recentUserChanges.humidity_threshold) {
        humidityThresholdInput.value = data.humidity_threshold;
        document.getElementById('humidityThresholdSlider').value = data.humidity_threshold;
    }
    if (buzzerHumidityThresholdInput && parseFloat(buzzerHumidityThresholdInput.value) !== data.buzzer_humidity_threshold && 
        !buzzerHumidityThresholdInput.matches(':focus') && !recentUserChanges.buzzer_humidity_threshold) {
        buzzerHumidityThresholdInput.value = data.buzzer_humidity_threshold;
        document.getElementById('buzzerHumidityThresholdSlider').value = data.buzzer_humidity_threshold;
    }
    
    document.getElementById('bufferInfo').textContent = `${data.buffer_size}/${data.buffer_max}`;
    
    // Update monitoring status buttons
    if (data.monitoring_active !== undefined) {
        isMonitoring = data.monitoring_active;
        const startBtn = document.getElementById('startSystem');
        const stopBtn = document.getElementById('stopSystem');
        const badge = document.getElementById('systemStatusBadge');
        
        if (startBtn) startBtn.disabled = isMonitoring;
        if (stopBtn) stopBtn.disabled = !isMonitoring;
        if (badge) {
            badge.innerHTML = isMonitoring ? 
                '<span class="badge running">System Running</span>' : 
                '<span class="badge idle">System Idle</span>';
        }
    }
    
    updateGlobalMode();
}

function updateModeBadge(elementId, manualState) {
    const badge = document.getElementById(elementId);
    if (!badge) return;
    if (manualState === true) {
        badge.textContent = 'MANUAL ON';
        badge.className = 'mode-badge manual-on';
    } else if (manualState === false) {
        badge.textContent = 'MANUAL OFF';
        badge.className = 'mode-badge manual-off';
    } else {
        badge.textContent = 'AUTO';
        badge.className = 'mode-badge auto';
    }
}

function updateDeviceLED(elementId, state) {
    const led = document.getElementById(elementId);
    if (state) led.classList.add('on');
    else led.classList.remove('on');
}

function updateBuzzerStatus(state) {
    const buzzerStatus = document.getElementById('buzzerStatus');
    const buzzerBadge = document.getElementById('buzzerBadge');
    const buzzerIcon = buzzerStatus.querySelector('.buzzer-icon');
    const buzzerText = buzzerStatus.querySelector('.buzzer-text');
    
    if (state) {
        buzzerStatus.classList.add('active');
        buzzerIcon.textContent = '🔊';
        buzzerText.textContent = 'ACTIVE';
        buzzerBadge.className = 'sensor-badge on';
        buzzerBadge.textContent = 'ON';
    } else {
        buzzerStatus.classList.remove('active');
        buzzerIcon.textContent = '🔇';
        buzzerText.textContent = 'Inactive';
        buzzerBadge.className = 'sensor-badge off';
        buzzerBadge.textContent = 'OFF';
    }
}

function updateGlobalMode() {
    const globalMode = document.getElementById('globalMode');
    const tempManual = window.currentData?.manual_temp_led;
    const humidityManual = window.currentData?.manual_humidity_led;
    const buzzerManual = window.currentData?.manual_buzzer;
    
    if (tempManual !== null || humidityManual !== null || buzzerManual !== null) {
        globalMode.textContent = '⚡ Manual Mode Active';
        globalMode.className = 'global-mode manual';
    } else {
        globalMode.textContent = '⚡ All Auto';
        globalMode.className = 'global-mode';
    }
}

function updateChart(data) {
    if (!chart || !data || data.length === 0) return;
    
    const labels = data.map(item => new Date(item.timestamp).toLocaleTimeString());
    const temperatures = data.map(item => item.temperature);
    const humidities = data.map(item => item.humidity);
    
    chart.data.labels = labels;
    chart.data.datasets[0].data = temperatures;
    chart.data.datasets[1].data = humidities;
    chart.update();
}

function updateBufferInfo(count) {
    document.getElementById('bufferInfo').textContent = `${count}/10`;
}

function showConnectionMessage(message, type) {
    const messageEl = document.getElementById('connectionMessage');
    messageEl.textContent = message;
    messageEl.className = `connection-message ${type}`;
    if (type === 'success') {
        setTimeout(() => messageEl.style.display = 'none', 5000);
    }
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        background: ${type === 'error' ? '#f56565' : type === 'success' ? '#48bb78' : type === 'warning' ? '#ed8936' : '#4299e1'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 5px 20px rgba(0,0,0,0.3);
        z-index: 1000;
        animation: slideIn 0.3s ease;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255,255,255,0.1);
        margin-bottom: 10px;
        max-width: 400px;
    `;
    
    // Stack notifications vertically
    const existingNotifications = document.querySelectorAll('.notification');
    let topOffset = 20;
    existingNotifications.forEach((notif, index) => {
        topOffset += 70; // Each notification is ~60px + 10px gap
        notif.style.top = topOffset + 'px';
    });
    
    document.body.appendChild(notification);
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

async function saveThresholds() {
    console.log('💾 saveThresholds function called');
    if (!activeDeviceId) {
        showNotification('Please select a device first', 'error');
        return;
    }
    
    if (!isConnected) {
        showNotification('Please connect to ESP32 first', 'error');
        return;
    }
    
    const tempVal = parseFloat(document.getElementById('tempThresholdInput').value);
    const buzzerTempVal = parseFloat(document.getElementById('buzzerTempThresholdInput').value);
    const humidityVal = parseFloat(document.getElementById('humidityThresholdInput').value);
    const buzzerHumidityVal = parseFloat(document.getElementById('buzzerHumidityThresholdInput').value);

    const thresholds = {
        temp_threshold: tempVal,
        buzzer_temp_threshold: buzzerTempVal,
        humidity_threshold: humidityVal,
        buzzer_humidity_threshold: buzzerHumidityVal
    };
    
    console.log('📤 Sending thresholds to backend:', thresholds);
    
    // Set local flags to prevent immediate overwrite by periodic updates
    recentUserChanges.temp_threshold = true;
    recentUserChanges.buzzer_temp_threshold = true;
    recentUserChanges.humidity_threshold = true;
    recentUserChanges.buzzer_humidity_threshold = true;
    
    try {
        const response = await fetch(`/api/devices/${activeDeviceId}/thresholds`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(thresholds)
        });
        const data = await response.json();
        console.log('📥 Backend response for thresholds:', data);
        
        if (response.ok) {
            showNotification(data.message || 'Thresholds updated successfully', 'success');
        } else {
            showNotification(data.message || 'Failed to save thresholds', 'error');
        }
    } catch (error) {
        console.error('❌ Save thresholds error:', error);
        showNotification('Failed to save thresholds', 'error');
    } finally {
        // Reset flags after a short delay
        setTimeout(() => {
            recentUserChanges.temp_threshold = false;
            recentUserChanges.buzzer_temp_threshold = false;
            recentUserChanges.humidity_threshold = false;
            recentUserChanges.buzzer_humidity_threshold = false;
            console.log('🔄 recentUserChanges flags reset');
        }, 3000);
    }
}

async function clearBuffer() {
    if (!isConnected) {
        showNotification('Please connect to ESP32 first', 'error');
        return;
    }
    try {
        const response = await fetch('/api/buffer/clear', { method: 'POST' });
        const data = await response.json();
        if (response.ok) {
            showNotification(data.message, 'success');
            await loadSensorHistory();
        }
    } catch (error) {
        console.error('Clear buffer error:', error);
        showNotification('Failed to clear buffer', 'error');
    }
}

async function refreshEvents() {
    if (!isConnected) return;
    try {
        const response = await fetch('/api/events');
        const events = await response.json();
        updateEventsLog(events);
        document.getElementById('eventCount').textContent = `${events.length} events`;
    } catch (error) {
        console.error('Error refreshing events:', error);
    }
}

function updateEventsLog(events) {
    const logContainer = document.getElementById('eventsLog');
    if (events.length === 0) {
        logContainer.innerHTML = '<div class="event-item">No events</div>';
        return;
    }
    let html = '';
    events.reverse().forEach(event => {
        const timeStr = new Date(event.timestamp).toLocaleTimeString();
        html += `
            <div class="event-item">
                <span class="event-timestamp">${timeStr}</span>
                <span class="event-type ${event.type}">${event.type}</span>
                <span class="event-description">${event.description}</span>
            </div>
        `;
    });
    logContainer.innerHTML = html;
}
