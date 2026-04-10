# SCADA Monitoring System - Temperature & Humidity with Cyclic Control

A complete SCADA-like monitoring system using ESP32, Modbus TCP, and Python backend with modern web frontend.

## Features

- 🌡️ **Dual Sensor Monitoring**: Temperature and Humidity using DHT11
- 💡 **Dual LEDs**: Separate LEDs for temperature and humidity alerts
- 🔊 **Common Buzzer**: Activates when either sensor exceeds critical threshold
- 🔄 **Cyclic Manual Control**: Single button cycles through AUTO → ON → OFF for each device
- 📊 **Real-time Charts**: Visual display of last 10 readings
- 🔌 **Persistent Connection**: Enter IP/port, stays connected until manual disconnect
- 💾 **Circular Buffer**: Automatically maintains last 10 readings (FIFO)
- 🎨 **Modern UI**: Glass morphism design with status indicators

## Hardware Requirements

- ESP32 Development Board
- DHT11 Temperature & Humidity Sensor
- 2x LEDs (or use built-in LED for temperature)
- 1x Buzzer
- Resistors (220Ω for LEDs)
- Breadboard and Jumper wires

## Wiring Diagram
