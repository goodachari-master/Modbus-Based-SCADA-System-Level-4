#include <WiFi.h>
#include <ModbusIP_ESP8266.h>
#include <DHT.h>
#include <ESPmDNS.h>  // For mDNS - allows device to be discovered by name

// Pin Definitions
#define LED_PIN 2          // Temperature LED (built-in LED)
#define HUMIDITY_LED_PIN 18 // Humidity LED (GPIO16)
#define BUZZER_PIN 4        // Common buzzer (GPIO4)
#define DHT_PIN 15          // DHT11 data pin (GPIO15)
#define DHT_TYPE DHT11

// WiFi Configuration - CHANGE THESE
const char* ssid = "YourWiFiSSID";
const char* password = "YourWiFiPassword";

// Room Configuration - CHANGE THIS FOR EACH ESP32
// Example: "Living Room", "Bedroom", "Kitchen", "Office", "Garage", etc.
String roomName = "Living Room";  // <-- CHANGE THIS FOR EACH ESP32
String deviceID = "esp32_living_room";  // <-- CHANGE THIS FOR EACH ESP32

// Modbus Registers
const int TEMP_REG = 0;           // Input Register for temperature
const int HUMIDITY_REG = 1;        // Input Register for humidity
const int TEMP_LED_COIL = 0;       // Coil for temperature LED
const int HUMIDITY_LED_COIL = 1;    // Coil for humidity LED
const int BUZZER_COIL = 2;          // Coil for common buzzer
const int ROOM_NAME_REG = 10;       // Holding register for room name (string)

ModbusIP mb;
DHT dht(DHT_PIN, DHT_TYPE);

// Device information
String firmwareVersion = "2.0.0";

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n\n=================================");
  Serial.println("ESP32 SCADA Sensor Node Starting");
  Serial.println("=================================");
  Serial.print("Room: ");
  Serial.println(roomName);
  Serial.print("Device ID: ");
  Serial.println(deviceID);
  
  // Initialize pins
  pinMode(LED_PIN, OUTPUT);
  pinMode(HUMIDITY_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  
  // Ensure all outputs are OFF at start
  digitalWrite(LED_PIN, LOW);
  digitalWrite(HUMIDITY_LED_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);
  
  // Initialize sensor
  dht.begin();
  Serial.println("DHT11 Sensor Initialized");
  
  // Connect to WiFi
  Serial.print("Connecting to WiFi");
  WiFi.begin(ssid, password);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ WiFi Connected!");
    Serial.print("ESP32 IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.print("MAC Address: ");
    Serial.println(WiFi.macAddress());
    
    // Setup mDNS for easy discovery
    String mdnsName = deviceID;
    mdnsName.replace(" ", "_");
    mdnsName.toLowerCase();
    
    if (!MDNS.begin(mdnsName.c_str())) {
      Serial.println("Error setting up MDNS responder!");
    } else {
      Serial.print("mDNS responder started: ");
      Serial.print(mdnsName);
      Serial.println(".local");
      MDNS.addService("modbus", "tcp", 502);
      MDNS.addServiceTxt("modbus", "tcp", "room", roomName);
      MDNS.addServiceTxt("modbus", "tcp", "device_id", deviceID);
    }
  } else {
    Serial.println("\n❌ WiFi Connection Failed!");
    Serial.println("Check your WiFi credentials");
  }
  
  // Setup Modbus Server
  mb.server();
  
  // Add Modbus registers
  mb.addIreg(TEMP_REG);           // Temperature input register
  mb.addIreg(HUMIDITY_REG);        // Humidity input register
  mb.addCoil(TEMP_LED_COIL);       // Temperature LED coil
  mb.addCoil(HUMIDITY_LED_COIL);   // Humidity LED coil
  mb.addCoil(BUZZER_COIL);         // Common buzzer coil
  mb.addHreg(ROOM_NAME_REG);       // Room name holding register
  
  // Store room name in holding registers (limited to 16 chars)
  String roomShort = roomName.length() > 16 ? roomName.substring(0, 16) : roomName;
  for (int i = 0; i < roomShort.length(); i++) {
    mb.Hreg(ROOM_NAME_REG + i, (int)roomShort.charAt(i));
  }
  mb.Hreg(ROOM_NAME_REG + roomShort.length(), 0); // Null terminator
  
  Serial.println("✅ Modbus Server Started");
  Serial.println("Register Map:");
  Serial.println("  IR0: Temperature (*10)");
  Serial.println("  IR1: Humidity (*10)");
  Serial.println("  Coil0: Temperature LED");
  Serial.println("  Coil1: Humidity LED");
  Serial.println("  Coil2: Common Buzzer");
  Serial.println("  HR10+: Room Name");
  Serial.println("=================================\n");
}

void loop() {
  // Handle Modbus requests
  mb.task();
  
  // Read temperature and humidity from DHT11
  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();
  
  // Update Modbus registers if readings are valid
  if (!isnan(temperature) && !isnan(humidity)) {
    // Store with 1 decimal precision (multiply by 10)
    mb.Ireg(TEMP_REG, (int)(temperature * 10));
    mb.Ireg(HUMIDITY_REG, (int)(humidity * 10));
    
    Serial.print("🌡️ ");
    Serial.print(roomName);
    Serial.print(" - Temperature: ");
    Serial.print(temperature);
    Serial.print(" °C | 💧 Humidity: ");
    Serial.print(humidity);
    Serial.println(" %");
  } else {
    Serial.print("❌ ");
    Serial.print(roomName);
    Serial.println(" - Failed to read DHT sensor!");
    // Send error values
    mb.Ireg(TEMP_REG, -999);
    mb.Ireg(HUMIDITY_REG, -999);
  }
  
  // Update physical outputs based on Modbus coil values
  digitalWrite(LED_PIN, mb.Coil(TEMP_LED_COIL));
  digitalWrite(HUMIDITY_LED_PIN, mb.Coil(HUMIDITY_LED_COIL));
  digitalWrite(BUZZER_PIN, mb.Coil(BUZZER_COIL));
  
  // Maintain mDNS
  MDNS.update();
  
  delay(2000); // Read every 2 seconds
}