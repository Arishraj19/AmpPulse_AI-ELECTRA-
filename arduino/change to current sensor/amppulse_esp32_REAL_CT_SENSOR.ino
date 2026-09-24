/*
  ========================================================================
  ESP32 Wireless Energy Monitoring & Control System
  AmpPulse AI - Measure Every Ampere. Save Every Rupee.
  ========================================================================

  HARDWARE:
  - ESP32-WROOM-DA
  - ZMPT101B AC Voltage Sensor (real)
  - DHT22 Temperature & Humidity Sensor (real)
  - SCT-013 Current Sensor (REAL - NOT SIMULATED)
  - 2-Channel Relay Module
  - RGB Status LED (discrete Red / Green / Blue LEDs)

  CURRENT MEASUREMENT:
  - Real CT sensor (SCT-013-010 or similar)
  - Burden resistor circuit (56Ω + 0.1µF capacitor)
  - ADC-based RMS calculation
  - Proper calibration factor for accurate Ampere measurement

  SETUP:
  1. Connect CT sensor secondary to burden circuit (56Ω + cap)
  2. Connect burden output to ESP32 ADC pin (GPIO35)
  3. Configure WIFI_SSID and WIFI_PASSWORD below
  4. Set CT_CALIBRATION_FACTOR based on your CT sensor model
  5. Upload and calibrate using known loads

  SAFETY:
  - CT sensor MUST be used for AC current measurement only
  - 230V AC mains are NOT directly connected to ESP32
  - Burden resistor circuit provides safe isolation
  - Never bypass the burden resistor or capacitor
  
  LAPTOP:
  Connect laptop and ESP32 to the same Wi-Fi.
  Open the IP address shown in Serial Monitor.
  Example: http://192.168.1.8

  STATUS LED:
  - RED (solid)    : Wi-Fi not connected
  - RED (blinking) : Wi-Fi connected, but voltage is below threshold
  - GREEN (solid)  : Wi-Fi connected and voltage is normal
  - BLUE (pulse)   : brief flash on every sensor read (activity heartbeat)
*/

#include <WiFi.h>
#include <WebServer.h>
#include <DHT.h>
#include <math.h>

// =====================================================
// Wi-Fi Configuration
// =====================================================

const char* WIFI_SSID = "HOME";
const char* WIFI_PASSWORD = "Home@4127";

// =====================================================
// Pin Configuration
// =====================================================

// Relay
#define RELAY1_PIN 25
#define RELAY2_PIN 26

// ZMPT101B analog output (voltage sensor)
#define ZMPT_PIN 34

// SCT-013 analog output (current sensor) - REAL SENSOR
// NOTE: GPIO35 is suitable for ADC input. GPIO34 is used for ZMPT.
// If GPIO35 is unavailable, you can use GPIO36 or GPIO39 instead.
#define CT_PIN 35

// DHT22
#define DHT_PIN 4
#define DHT_TYPE DHT22

// Status LED (discrete R/G/B LEDs, each through its own resistor)
#define LED_RED_PIN 27
#define LED_GREEN_PIN 14
#define LED_BLUE_PIN 32

// =====================================================
// Web Server
// =====================================================

WebServer server(80);
DHT dht(DHT_PIN, DHT_TYPE);

// =====================================================
// Sensor Variables
// =====================================================

float voltage = 0.0;        // AC voltage (V)
float current = 0.0;        // AC current (A) - NOW REAL from CT sensor
float power = 0.0;          // Apparent power (W)
float energy = 0.0;         // Cumulative energy (kWh)

float temperature = 0.0;
float humidity = 0.0;

// Set once the first sensor read completes
bool sensorsInitialized = false;

// =====================================================
// Relay States
// =====================================================

bool relay1 = false;
bool relay2 = false;

// =====================================================
// Timing
// =====================================================

unsigned long lastSensorRead = 0;
unsigned long lastEnergyUpdate = 0;

const unsigned long SENSOR_INTERVAL = 2000;    // Read sensors every 2 seconds
const unsigned long ENERGY_INTERVAL = 60000;   // Update energy every 60 seconds

// =====================================================
// CURRENT SENSOR CONFIGURATION
// =====================================================
//
// SCT-013 CT Sensor Settings
//
// Model: SCT-013-010 (10A max, 2000:1 turns ratio)
// Burden Resistor: 56Ω (provides ~0.28V at 5A)
// Interface Circuit: 56Ω + 0.1µF capacitor (AC coupling)
//
// CALIBRATION FACTOR:
// This value converts the RMS ADC reading to Amperes.
// Starting value for SCT-013-010 with 56Ω burden: ~0.0234
//
// HOW TO FIND YOUR CALIBRATION FACTOR:
// 1. Use a known 1000W load (heater, toaster, etc.)
// 2. Clip CT sensor around the mains wire
// 3. Record ESP32 reading (e.g., 4.20A)
// 4. Measure with AC clamp meter (e.g., 4.35A)
// 5. Calculate: new_factor = old_factor × (multimeter_reading / ESP32_reading)
//              = 0.0234 × (4.35 / 4.20) = 0.0243
// 6. Update this value and retest until within ±2% accuracy
//
// IMPORTANT: Adjust this based on YOUR hardware!
//

#define CT_CALIBRATION_FACTOR 0.0234          // Change based on calibration testing
#define CT_ADC_SAMPLES 1000                   // Number of ADC samples for RMS calc
#define CT_AVERAGING_SAMPLES 100              // Number of readings to average
#define CT_CURRENT_THRESHOLD_ON 0.1           // If current > 0.1A, device is ON
#define NOMINAL_VOLTAGE 230.0                 // Assumed nominal voltage (V) - measured by ZMPT
#define POWER_FACTOR 0.95                     // Typical power factor for resistive loads
#define ELECTRICITY_UNIT_RATE 6.0             // Electricity cost per kWh (₹) - India

// Current reading buffer for averaging
float currentReadings[CT_AVERAGING_SAMPLES];
int currentReadIndex = 0;
float currentSum = 0.0;

// Device ON/OFF status
bool deviceOn = false;

// =====================================================
// ZMPT101B Calibration
// =====================================================
//
// Voltage sensor calibration value.
// For ZMPT101B, typical value is 0.325
// Adjust based on your specific module.
//

float ZMPT_CALIBRATION = 0.325;

// =====================================================
// Status LED Configuration
// =====================================================

const float LOW_VOLTAGE_THRESHOLD = 200.0;

// Non-blocking red blink timing
const unsigned long BLINK_INTERVAL = 400;
unsigned long lastBlinkToggle = 0;
bool blinkState = false;

// Non-blocking blue activity pulse timing
const unsigned long BLUE_ACTIVITY_DURATION = 150;
unsigned long blueActivityUntil = 0;

// =====================================================
// CURRENT SENSOR - RMS CALCULATION
// =====================================================
//
// Read AC current waveform from CT sensor
// Calculate Root Mean Square (RMS) value
// Apply calibration factor to get Amperes
//
// This is the REAL current measurement (not simulated)
//

float readCurrentFromCT() {

  // -----
  // Stage 1: Read ADC samples and find DC offset
  // -----

  float sum = 0.0;
  
  for (int i = 0; i < CT_ADC_SAMPLES; i++) {
    int adcValue = analogRead(CT_PIN);
    sum += adcValue;
    delayMicroseconds(200);  // 200µs between samples = ~5kHz sampling
  }
  
  float offset = sum / CT_ADC_SAMPLES;

  // -----
  // Stage 2: Calculate RMS of AC waveform (remove DC offset)
  // -----

  float squareSum = 0.0;
  
  for (int i = 0; i < CT_ADC_SAMPLES; i++) {
    int adcValue = analogRead(CT_PIN);
    float value = adcValue - offset;
    squareSum += value * value;
    delayMicroseconds(200);
  }
  
  float rms = sqrt(squareSum / CT_ADC_SAMPLES);

  // -----
  // Stage 3: Convert RMS ADC to voltage, then to Amperes
  // -----

  // Convert ADC value to voltage (12-bit ADC, 11dB attenuation = 0-3.3V range)
  float rmsVoltage = rms * (3.3 / 4095.0);

  // Apply calibration factor to get Amperes
  // Calibration factor accounts for:
  // - CT turns ratio (2000:1)
  // - Burden resistor value (56Ω)
  // - ADC scaling
  float currentAmps = rmsVoltage * CT_CALIBRATION_FACTOR;

  // -----
  // Stage 4: Apply averaging filter for stable reading
  // -----

  currentSum -= currentReadings[currentReadIndex];
  currentReadings[currentReadIndex] = currentAmps;
  currentSum += currentAmps;
  currentReadIndex = (currentReadIndex + 1) % CT_AVERAGING_SAMPLES;

  float averagedCurrent = currentSum / CT_AVERAGING_SAMPLES;

  // -----
  // Stage 5: Noise floor - treat very small values as zero
  // -----
  // If current is less than 0.02A, consider it zero (noise floor)
  
  if (averagedCurrent < 0.02) {
    averagedCurrent = 0.0;
  }

  return averagedCurrent;
}

// =====================================================
// VOLTAGE SENSOR - RMS CALCULATION
// =====================================================
//
// Read AC voltage from ZMPT101B sensor
// This code already existed and is unchanged
//

float readVoltage() {

  const int samples = 500;
  float sum = 0;

  // Find ADC average / offset
  for (int i = 0; i < samples; i++) {
    int adcValue = analogRead(ZMPT_PIN);
    sum += adcValue;
    delayMicroseconds(200);
  }

  float offset = sum / samples;

  // Calculate RMS
  float squareSum = 0;

  for (int i = 0; i < samples; i++) {
    int adcValue = analogRead(ZMPT_PIN);
    float value = adcValue - offset;
    squareSum += value * value;
    delayMicroseconds(200);
  }

  float rms = sqrt(squareSum / samples);

  // Convert to AC voltage
  float result = rms * ZMPT_CALIBRATION;

  return result;
}

// =====================================================
// POWER CALCULATION
// =====================================================
//
// Calculate apparent power using REAL measured current
// Power (W) = Voltage (V) × Current (A) × Power Factor
//
// Note: If power factor is not measured, we use a typical value (0.95)
// For purely resistive loads, PF = 1.0
//

float calculatePower(float volts, float amps) {
  // Apparent power = V × A × PF
  return volts * amps * POWER_FACTOR;
}

// =====================================================
// DEVICE STATUS DETECTION
// =====================================================
//
// Determine if device is ON or OFF based on measured current
// If current exceeds threshold, device is ON
// Otherwise, device is OFF
//

bool isDeviceOn(float currentAmps) {
  return (currentAmps > CT_CURRENT_THRESHOLD_ON);
}

// =====================================================
// ENERGY CALCULATION
// =====================================================
//
// Track cumulative energy consumption over time
// Energy (kWh) = Power (W) × Time (hours) / 1,000,000
//
// Note: This is a simple accumulation. For production systems,
// store to non-volatile memory (EEPROM/SPIFFS) to persist across resets.
//

unsigned long lastEnergyTime = 0;

void updateEnergy() {
  unsigned long currentTime = millis();
  
  if (lastEnergyTime == 0) {
    lastEnergyTime = currentTime;
    return;
  }
  
  // Time elapsed in seconds
  float elapsedSeconds = (currentTime - lastEnergyTime) / 1000.0;
  lastEnergyTime = currentTime;

  // Energy increment = (Power in W × Time in hours) / 1,000,000
  // = (Power in W × elapsedSeconds / 3600) / 1,000,000
  float energyIncrement = (power * elapsedSeconds / 3600.0) / 1000.0;
  
  energy += energyIncrement;
}

// =====================================================
// ESTIMATED ELECTRICITY COST
// =====================================================
//
// Calculate estimated cost based on consumed energy
// Cost (₹) = Energy (kWh) × Unit Rate (₹/kWh)
//

float calculateEstimatedCost(float energyKwh) {
  return energyKwh * ELECTRICITY_UNIT_RATE;
}

// =====================================================
// Read All Sensors
// =====================================================

void readSensors() {

  // Voltage (real sensor)
  voltage = readVoltage();

  // Current (REAL from CT sensor - replaces simulation!)
  current = readCurrentFromCT();

  // Power (calculated from real V and A)
  power = calculatePower(voltage, current);

  // Device status (based on real current)
  deviceOn = isDeviceOn(current);

  // Temperature
  temperature = dht.readTemperature();

  // Humidity
  humidity = dht.readHumidity();

  // Handle DHT errors
  if (isnan(temperature)) {
    temperature = 0;
  }

  if (isnan(humidity)) {
    humidity = 0;
  }

  // Update cumulative energy
  updateEnergy();

  // -----
  // SERIAL MONITOR OUTPUT
  // -----
  // Display all measurements for debugging and verification

  Serial.println();
  Serial.println("=====================================");
  Serial.println("AmpPulse AI - Real Current Measurement");
  Serial.println("=====================================");

  Serial.print("Voltage           : ");
  Serial.print(voltage, 1);
  Serial.println(" V (ZMPT101B)");

  Serial.print("Current           : ");
  Serial.print(current, 2);
  Serial.println(" A (SCT-013 CT Sensor - REAL!)");

  Serial.print("Power             : ");
  Serial.print(power, 1);
  Serial.println(" W");

  Serial.print("Power (kW)        : ");
  Serial.print(power / 1000.0, 3);
  Serial.println(" kW");

  Serial.print("Energy            : ");
  Serial.print(energy, 3);
  Serial.println(" kWh");

  Serial.print("Estimated Cost    : ₹");
  Serial.print(calculateEstimatedCost(energy), 2);
  Serial.println();

  Serial.print("Temperature       : ");
  Serial.print(temperature, 1);
  Serial.println(" °C");

  Serial.print("Humidity          : ");
  Serial.print(humidity, 1);
  Serial.println(" %");

  Serial.print("Device Status     : ");
  Serial.println(deviceOn ? "ON (Current > 0.1A)" : "OFF");

  Serial.print("Relay 1           : ");
  Serial.println(relay1 ? "ON" : "OFF");

  Serial.print("Relay 2           : ");
  Serial.println(relay2 ? "ON" : "OFF");

  Serial.println("=====================================");

  // Status LED: mark data valid + trigger activity pulse
  sensorsInitialized = true;
  blueActivityUntil = millis() + BLUE_ACTIVITY_DURATION;
}

// =====================================================
// Status LED Control
// =====================================================

void setStatusLED(bool red, bool green, bool blue) {
  digitalWrite(LED_RED_PIN, red ? HIGH : LOW);
  digitalWrite(LED_GREEN_PIN, green ? HIGH : LOW);
  digitalWrite(LED_BLUE_PIN, blue ? HIGH : LOW);
}

void updateStatusLED() {

  bool wifiConnected = (WiFi.status() == WL_CONNECTED);
  bool blueActive = (millis() < blueActivityUntil);

  if (!wifiConnected) {
    setStatusLED(true, false, blueActive);
    return;
  }

  bool lowVoltage =
    sensorsInitialized &&
    (voltage < LOW_VOLTAGE_THRESHOLD);

  if (lowVoltage) {
    if (millis() - lastBlinkToggle >= BLINK_INTERVAL) {
      lastBlinkToggle = millis();
      blinkState = !blinkState;
    }
    setStatusLED(blinkState, false, blueActive);
  } else {
    setStatusLED(false, true, blueActive);
  }
}

// =====================================================
// CORS + Response Helper
// =====================================================

void sendResponse(int code, const char* type, const String& body) {

  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
  server.sendHeader("Cache-Control", "no-store");

  server.send(code, type, body);
}

void handleNotFound() {

  if (server.method() == HTTP_OPTIONS) {
    server.sendHeader("Access-Control-Allow-Origin", "*");
    server.sendHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
    server.sendHeader("Cache-Control", "no-store");
    server.send(204, "text/plain", "");
    return;
  }

  sendResponse(404, "text/plain", "Not found");
}

// =====================================================
// JSON Data Endpoint
// =====================================================
//
// This is the CLOUD/DASHBOARD DATA section
// Returns all sensor readings in JSON format
// CURRENT is now REAL (from CT sensor)
//

void handleData() {

  String json = "{";

  json += "\"voltage\":";
  json += String(voltage, 1);

  json += ",\"current\":";
  json += String(current, 2);        // REAL current from CT sensor

  json += ",\"power\":";
  json += String(power, 1);

  json += ",\"energy\":";
  json += String(energy, 3);

  json += ",\"estimatedCost\":";
  json += String(calculateEstimatedCost(energy), 2);

  json += ",\"temperature\":";
  json += String(temperature, 1);

  json += ",\"humidity\":";
  json += String(humidity, 1);

  json += ",\"deviceStatus\":";
  json += deviceOn ? "\"ON\"" : "\"OFF\"";

  json += ",\"relay1\":";
  json += relay1 ? "true" : "false";

  json += ",\"relay2\":";
  json += relay2 ? "true" : "false";

  json += ",\"sensorType\":\"SCT-013 CT Sensor (Real Current)\"";

  json += "}";

  sendResponse(200, "application/json", json);
}

// =====================================================
// Relay 1 Control
// =====================================================

void relay1On() {
  relay1 = true;
  digitalWrite(RELAY1_PIN, LOW);
  sendResponse(200, "text/plain", "Relay 1 ON");
  Serial.println("Relay 1 -> ON");
}

void relay1Off() {
  relay1 = false;
  digitalWrite(RELAY1_PIN, HIGH);
  sendResponse(200, "text/plain", "Relay 1 OFF");
  Serial.println("Relay 1 -> OFF");
}

// =====================================================
// Relay 2 Control
// =====================================================

void relay2On() {
  relay2 = true;
  digitalWrite(RELAY2_PIN, LOW);
  sendResponse(200, "text/plain", "Relay 2 ON");
  Serial.println("Relay 2 -> ON");
}

void relay2Off() {
  relay2 = false;
  digitalWrite(RELAY2_PIN, HIGH);
  sendResponse(200, "text/plain", "Relay 2 OFF");
  Serial.println("Relay 2 -> OFF");
}

// =====================================================
// Main Web Page (HTML/CSS/JS)
// =====================================================

void handleRoot() {

  String html = R"rawliteral(

<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AmpPulse AI - Energy Monitor</title>
<style>
body {
  font-family: Arial, sans-serif;
  background: #f2f2f2;
  margin: 0;
  padding: 20px;
  text-align: center;
}
.container {
  max-width: 800px;
  margin: auto;
}
h1 {
  margin-bottom: 25px;
  color: #333;
}
.card {
  background: white;
  padding: 20px;
  margin-bottom: 18px;
  border-radius: 15px;
  box-shadow: 0 3px 10px rgba(0,0,0,0.15);
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 15px;
}
.parameter {
  background: #fafafa;
  padding: 15px;
  border-radius: 10px;
}
.label {
  font-size: 14px;
  color: #666;
}
.value {
  font-size: 28px;
  font-weight: bold;
  margin-top: 8px;
  color: #2196F3;
}
.unit {
  font-size: 12px;
  color: #999;
}
button {
  border: none;
  padding: 12px 25px;
  margin: 5px;
  border-radius: 8px;
  font-size: 16px;
  cursor: pointer;
  transition: opacity 0.2s;
}
button:hover {
  opacity: 0.8;
}
.on {
  background: #4CAF50;
  color: white;
}
.off {
  background: #f44336;
  color: white;
}
.status {
  font-weight: bold;
  margin: 10px;
  font-size: 18px;
}
.status.on {
  color: #4CAF50;
}
.status.off {
  color: #f44336;
}
.connected {
  color: #4CAF50;
  font-weight: bold;
}
.info {
  background: #e3f2fd;
  padding: 10px;
  border-radius: 8px;
  font-size: 12px;
  color: #1976d2;
  margin-top: 10px;
}
</style>
</head>
<body>

<div class="container">

<h1>⚡ AmpPulse AI</h1>
<h2>Energy Monitoring System</h2>

<div class="card">
<h2>Electrical Parameters</h2>
<div class="grid">
<div class="parameter">
  <div class="label">Voltage</div>
  <div class="value"><span id="voltage">0.0</span><span class="unit">V</span></div>
</div>
<div class="parameter">
  <div class="label">Current (CT)</div>
  <div class="value"><span id="current">0.00</span><span class="unit">A</span></div>
</div>
<div class="parameter">
  <div class="label">Power</div>
  <div class="value"><span id="power">0.0</span><span class="unit">W</span></div>
</div>
<div class="parameter">
  <div class="label">Energy</div>
  <div class="value"><span id="energy">0.000</span><span class="unit">kWh</span></div>
</div>
<div class="parameter">
  <div class="label">Estimated Cost</div>
  <div class="value">₹<span id="cost">0.00</span></div>
</div>
<div class="parameter">
  <div class="label">Device Status</div>
  <div class="value"><span id="deviceStatus">OFF</span></div>
</div>
</div>
</div>

<div class="card">
<h2>Environment</h2>
<div class="grid">
<div class="parameter">
  <div class="label">Temperature</div>
  <div class="value"><span id="temperature">0.0</span><span class="unit">°C</span></div>
</div>
<div class="parameter">
  <div class="label">Humidity</div>
  <div class="value"><span id="humidity">0.0</span><span class="unit">%</span></div>
</div>
</div>
</div>

<div class="card">
<h2>Wireless Device Control</h2>

<h3>Relay 1</h3>
<button class="on" onclick="relay1Control('on')">ON</button>
<button class="off" onclick="relay1Control('off')">OFF</button>
<div class="status" id="relay1Status">OFF</div>

<hr>

<h3>Relay 2</h3>
<button class="on" onclick="relay2Control('on')">ON</button>
<button class="off" onclick="relay2Control('off')">OFF</button>
<div class="status" id="relay2Status">OFF</div>
</div>

<div class="card">
<p class="connected">● ESP32 Connected</p>
<p>Live data updates every 2 seconds</p>
<div class="info">
  Current Sensor: SCT-013 CT Sensor (Real Measurement - Not Simulated)
</div>
</div>

</div>

<script>

function updateData() {
  fetch('/data')
    .then(response => response.json())
    .then(data => {
      document.getElementById('voltage').innerText = Number(data.voltage).toFixed(1);
      document.getElementById('current').innerText = Number(data.current).toFixed(2);
      document.getElementById('power').innerText = Number(data.power).toFixed(1);
      document.getElementById('energy').innerText = Number(data.energy).toFixed(3);
      document.getElementById('cost').innerText = Number(data.estimatedCost).toFixed(2);
      
      const deviceStatus = data.deviceStatus === 'ON' ? 'ON' : 'OFF';
      document.getElementById('deviceStatus').innerText = deviceStatus;
      document.getElementById('deviceStatus').className = 'value ' + (deviceStatus === 'ON' ? 'on' : 'off');
      
      document.getElementById('temperature').innerText = Number(data.temperature).toFixed(1);
      document.getElementById('humidity').innerText = Number(data.humidity).toFixed(1);
      
      const relay1 = data.relay1 ? 'ON' : 'OFF';
      const relay2 = data.relay2 ? 'ON' : 'OFF';
      document.getElementById('relay1Status').innerText = relay1;
      document.getElementById('relay1Status').className = 'status ' + (relay1 === 'ON' ? 'on' : 'off');
      document.getElementById('relay2Status').innerText = relay2;
      document.getElementById('relay2Status').className = 'status ' + (relay2 === 'ON' ? 'on' : 'off');
    })
    .catch(error => console.log("Connection error:", error));
}

function relay1Control(state) {
  fetch('/relay1/' + state)
    .then(() => { updateData(); });
}

function relay2Control(state) {
  fetch('/relay2/' + state)
    .then(() => { updateData(); });
}

setInterval(updateData, 2000);
updateData();

</script>

</body>
</html>

)rawliteral";

  sendResponse(200, "text/html", html);
}

// =====================================================
// Setup - Initialization
// =====================================================

void setup() {

  // Serial
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println();
  Serial.println("=====================================");
  Serial.println("AmpPulse AI - Energy Monitoring");
  Serial.println("Real CT Sensor (SCT-013) Firmware");
  Serial.println("=====================================");

  // Initialize current readings buffer
  for (int i = 0; i < CT_AVERAGING_SAMPLES; i++) {
    currentReadings[i] = 0.0;
  }

  // Relay
  pinMode(RELAY1_PIN, OUTPUT);
  pinMode(RELAY2_PIN, OUTPUT);
  digitalWrite(RELAY1_PIN, HIGH);  // OFF
  digitalWrite(RELAY2_PIN, HIGH);  // OFF

  // Status LED
  pinMode(LED_RED_PIN, OUTPUT);
  pinMode(LED_GREEN_PIN, OUTPUT);
  pinMode(LED_BLUE_PIN, OUTPUT);
  setStatusLED(true, false, false);  // Red while initializing

  // ZMPT101B (voltage)
  pinMode(ZMPT_PIN, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(ZMPT_PIN, ADC_11db);

  // SCT-013 (current) - REAL SENSOR
  pinMode(CT_PIN, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(CT_PIN, ADC_11db);

  Serial.print("CT Sensor ADC Pin: GPIO");
  Serial.println(CT_PIN);
  Serial.print("CT Calibration Factor: ");
  Serial.println(CT_CALIBRATION_FACTOR, 4);

  // DHT22
  dht.begin();

  // Wi-Fi
  Serial.println("Connecting to Wi-Fi...");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("Wi-Fi connected!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());

  // Web Server
  server.on("/", HTTP_GET, handleRoot);
  server.on("/data", HTTP_GET, handleData);
  server.on("/relay1/on", HTTP_GET, relay1On);
  server.on("/relay1/off", HTTP_GET, relay1Off);
  server.on("/relay2/on", HTTP_GET, relay2On);
  server.on("/relay2/off", HTTP_GET, relay2Off);
  server.onNotFound(handleNotFound);

  server.begin();

  Serial.println("Web server started.");
  Serial.println();
  Serial.print("Open in laptop: http://");
  Serial.println(WiFi.localIP());
  Serial.println();

  // First Sensor Reading
  readSensors();
  updateStatusLED();

  Serial.println("System ready!");
  Serial.println();
}

// =====================================================
// Main Loop
// =====================================================

void loop() {

  // Handle browser requests
  server.handleClient();

  // Read sensors periodically
  if (millis() - lastSensorRead >= SENSOR_INTERVAL) {
    lastSensorRead = millis();
    readSensors();
  }

  // Update status LED
  updateStatusLED();
}
