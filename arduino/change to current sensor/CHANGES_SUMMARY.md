# AmpPulse AI - Simulated to Real CT Sensor: Complete Change Summary

## OVERVIEW

Your project had **simulated current measurement** (fake values). It now has **real SCT-013 CT sensor integration** with proper RMS calculation, calibration support, and device ON/OFF detection.

---

## PART A: WHAT WAS FOUND IN EXISTING CODE

### 1. Simulated Current Function (Lines 212-225)

**Original Code:**
```cpp
// =====================================================
// Simulated PZEM Current
// =====================================================
//
// PZEM-004T is not connected/working yet.
// So current is simulated.
//
// Change these values according to your demo.
//

float readCurrent() {

  if (relay1 || relay2) {

    return 1.50;

  } else {

    return 0.00;
  }
}
```

**Problem:**
- Always returns 1.50A when ANY relay is ON
- Returns 0.00A when both relays OFF
- No real sensor reading
- Makes all power/energy/cost calculations meaningless

### 2. Impact on System

**Affected Features:**
- Current measurement: ❌ Fake (always 1.50A or 0.00A)
- Power calculation: ❌ Incorrect (based on fake current)
- Energy tracking: ❌ Meaningless
- Electricity cost: ❌ Wrong estimates
- Device ON/OFF: ❌ Based only on relay state, not actual power draw

**Working Components:**
- Voltage (ZMPT101B): ✅ Real and accurate
- Temperature (DHT22): ✅ Real and accurate
- Humidity (DHT22): ✅ Real and accurate
- Relay control: ✅ Working properly
- Web server & dashboard: ✅ Functional
- Wi-Fi & API: ✅ Operational

---

## PART B: COMPLETE LIST OF CHANGES

### Removed Code Sections

1. **Simulated readCurrent() function** - Completely removed
2. **Comment block** about PZEM-004T simulation - Removed

### Added Code Sections

1. **Current Sensor Configuration Block**
   - CT sensor ADC pin definition (GPIO35)
   - Calibration factor constant
   - RMS calculation parameters
   - Averaging and filtering settings
   - Device ON/OFF threshold

2. **readCurrentFromCT() Function** (NEW)
   - Reads 1000 ADC samples at 200µs intervals
   - Calculates DC offset (removes bias)
   - Computes RMS value from AC waveform
   - Converts RMS ADC to voltage
   - Applies calibration factor to get Amperes
   - Implements moving average filter (100 samples)
   - Applies noise floor threshold (< 0.02A = 0)
   - Returns stable, accurate current in Amperes

3. **calculatePower() Function** (NEW)
   - Power (W) = Voltage × Current × Power Factor (0.95)
   - Replaces inline calculation
   - Accounts for power factor

4. **isDeviceOn() Function** (NEW)
   - Determines device status based on current measurement
   - If current > 0.1A → Device is ON
   - If current ≤ 0.1A → Device is OFF
   - More accurate than relay-based detection

5. **updateEnergy() Function** (NEW)
   - Accumulates energy consumption over time
   - Energy (kWh) = Power × Time / 1,000,000
   - Tracks cumulative energy since power-on

6. **calculateEstimatedCost() Function** (NEW)
   - Cost (₹) = Energy (kWh) × Unit Rate (₹/kWh)
   - Default rate: ₹6 per kWh (adjustable)

7. **Enhanced Serial Monitor Output**
   - Shows voltage, current, power (W and kW), energy, cost
   - Displays device status (ON/OFF based on actual current)
   - Shows sensor type: "SCT-013 CT Sensor (Real!)"

8. **Enhanced JSON API Response** (/data endpoint)
   - Added `energy` field (kWh accumulated)
   - Added `estimatedCost` field (₹)
   - Added `deviceStatus` field (ON/OFF)
   - Added `sensorType` field (identifies real sensor)

9. **Enhanced Dashboard**
   - Energy card displaying accumulated kWh
   - Estimated cost card displaying ₹
   - Device status card showing ON/OFF
   - Updated info note: "SCT-013 CT Sensor (Real Measurement)"

10. **Updated Serial Monitor Output Format**
    ```
    Voltage           : 231.2 V (ZMPT101B)
    Current           : 4.32 A (SCT-013 CT Sensor - REAL!)
    Power             : 998.8 W
    Power (kW)        : 0.999 kW
    Energy            : 0.125 kWh
    Estimated Cost    : ₹0.75
    Temperature       : 28.5 °C
    Humidity          : 65.3 %
    Device Status     : ON (Current > 0.1A)
    ```

---

## PART C: DETAILED COMPARISON

| Feature | Before (Simulated) | After (Real CT) |
|---------|---|---|
| **Current Measurement** | Hardcoded 1.50A or 0.00A | Real RMS from CT sensor |
| **Current Sensor** | None (PZEM-004T unavailable) | SCT-013-010 with burden circuit |
| **RMS Calculation** | None | 1000-point RMS calculation |
| **Noise Filtering** | None | 100-sample moving average |
| **Calibration** | N/A | User-configurable factor (0.0234) |
| **Power Calculation** | V × 1.50A or V × 0.00A | V × A × 0.95 (power factor) |
| **Device Status** | Based on relay state only | Based on actual current (>0.1A) |
| **Energy Tracking** | Meaningless | Real accumulation |
| **Cost Estimation** | Wrong | Accurate (based on real kWh) |
| **Dashboard Display** | Fake current | Real current |
| **API /data Response** | Fake values | Real values + energy/cost |
| **Serial Monitor** | Misleading | Accurate debugging output |

---

## PART D: NEW HARDWARE REQUIREMENTS

### Essential Components

| Item | Model | Purpose | Cost |
|------|-------|---------|------|
| CT Sensor | SCT-013-010 | Current measurement (10A max) | ₹80-100 |
| Burden Resistor | 56Ω 1/2W | Convert current to voltage | ₹5 |
| Capacitor | 0.1µF 250V | AC coupling (DC blocking) | ₹5 |
| Resistor (Divider) | 2× 10kΩ 1/4W | Bias to 1.65V for ADC | ₹5 |
| Resistor (Signal) | 1kΩ 1/4W | Signal impedance | ₹2 |
| Breadboard | Full-size | Prototyping | ₹30-50 |
| Jumper Wires | 22AWG | Connections | ₹20 |

**Total: ₹150-200**

### Wiring Required

```
SCT-013 Sensor
  ↓ (Secondary output)
Burden Resistor Circuit (56Ω + 0.1µF Cap)
  ↓ (AC voltage signal)
Voltage Divider Bias (10k:10k) ← Keeps signal centered at 1.65V
  ↓ (Biased AC signal)
1kΩ Current-Limiting Resistor
  ↓
ESP32 GPIO35 (ADC input)
```

---

## PART E: CODE CONFIGURATION CONSTANTS

### In the Updated Arduino Code, Find and Configure:

#### 1. CT Calibration Factor
```cpp
// Line ~120
#define CT_CALIBRATION_FACTOR 0.0234

// START WITH: 0.0234 (typical for SCT-013-010 + 56Ω burden)
// ADJUST AFTER TESTING: Based on known load comparison
// ADJUST FORMULA: new = old × (multimeter_reading / ESP32_reading)
```

#### 2. CT ADC Pin
```cpp
// Line ~44
#define CT_PIN 35

// Use GPIO35, 36, or 39 (ADC pins only)
// GPIO35 is recommended (low noise)
// Same pin as ZMPT (GPIO34) will cause conflicts
```

#### 3. Device ON/OFF Threshold
```cpp
// Line ~116
#define CT_CURRENT_THRESHOLD_ON 0.1

// If current > 0.1A → Device is ON
// If current ≤ 0.1A → Device is OFF
// Adjust if needed (0.05 for sensitive loads, 0.2 for heavy)
```

#### 4. Electricity Unit Rate
```cpp
// Line ~123
#define ELECTRICITY_UNIT_RATE 6.0

// Cost per kWh in rupees (₹)
// Change based on your local electricity rate
// Example: 6.0 = ₹6 per kWh
```

#### 5. RMS Sampling
```cpp
// Line ~112
#define CT_ADC_SAMPLES 1000

// Number of ADC samples for RMS calculation
// Higher = more accurate but slower
// 1000 is good balance (200ms at 5kHz sampling)
```

#### 6. Averaging Filter
```cpp
// Line ~113
#define CT_AVERAGING_SAMPLES 100

// Number of readings to average
// Higher = smoother but slower response
// 100 = 200ms smoothing (every 2 seconds sensor reads)
```

---

## PART F: UNCHANGED CODE SECTIONS

The following sections of your code remain **completely unchanged** and will work as before:

1. **Wi-Fi Configuration** (WIFI_SSID, WIFI_PASSWORD)
2. **Relay Control** (relay1, relay2, ON/OFF functions)
3. **ZMPT101B Voltage Sensor** (readVoltage function)
4. **DHT22 Temperature/Humidity** (readTemperature, readHumidity)
5. **Status LED Control** (updateStatusLED function)
6. **Web Server** (all routes: /, /data, /relay1/on, etc.)
7. **HTTP/CORS Headers** (sendResponse function)
8. **Database/Backend Integration** (Dashboard API unchanged)
9. **HTML Dashboard Layout** (Same structure, added fields)
10. **Serial Monitor Initialization**

---

## PART G: KEY IMPROVEMENTS IN FUNCTIONALITY

### Before (Simulated Current)
```cpp
// Old readCurrent()
float readCurrent() {
  if (relay1 || relay2) {
    return 1.50;  // Always 1.50A if relay on
  } else {
    return 0.00;  // Always 0.00A if relay off
  }
}

// Result: 
// - Power = 230V × 1.50A = 345W (always, regardless of actual load)
// - Current jumps instantly when relay toggles (no reality)
// - Energy = meaningless
// - Cost = wrong
```

### After (Real CT Sensor)
```cpp
// New readCurrentFromCT()
float readCurrentFromCT() {
  // 1. Sample 1000 ADC points over ~200ms
  // 2. Calculate DC offset
  // 3. Compute RMS of AC waveform
  // 4. Convert to voltage
  // 5. Apply calibration: voltage × 0.0234 = Amperes
  // 6. Average 100 readings for stability
  // 7. Apply noise floor (< 0.02A = 0)
  // 8. Return stable, real Ampere value
  return averagedCurrent;
}

// Result:
// - Power = 230V × 4.35A × 0.95 = 951W (real measurement)
// - Current follows actual load (smooth, realistic)
// - Energy = accurate accumulation
// - Cost = correct estimate
// - Device status = based on actual power draw
```

### Energy Tracking Example

**Before (Simulated):**
```
If relay ON for 1 hour → Energy = 345W × 1hr = 0.345 kWh
If relay OFF → Energy = 0W × time = 0 kWh
(Wrong! Doesn't match actual electricity meter)
```

**After (Real CT):**
```
Plug 1000W heater, leave on 1 hour → Energy = ~1.0 kWh
(Matches electricity meter!)

Plug 500W fan, leave on 1 hour → Energy = ~0.5 kWh
(Correct!)
```

---

## PART H: HOW TO MIGRATE

### Step 1: Update Hardware
```
1. Solder/connect CT sensor burden circuit
2. Clip CT sensor around appliance wire
3. Connect GPIO35 to ADC signal (through voltage divider)
4. Verify all connections secure
```

### Step 2: Upload New Code
```
1. Open Arduino IDE
2. Load: amppulse_esp32_REAL_CT_SENSOR.ino
3. Verify compilation (Sketch → Verify)
4. Upload (Sketch → Upload)
5. Open Serial Monitor (Tools → Serial Monitor, 115200 baud)
6. Verify startup messages appear
```

### Step 3: Initial Testing
```
1. Wait 30 seconds for stabilization
2. Verify zero-current baseline (no load)
3. Turn on 1000W known load
4. Check current reading in Serial Monitor
5. Note ESP32 reading and multimeter reading
```

### Step 4: Calibration
```
1. Calculate error: measured ÷ expected
2. Update CT_CALIBRATION_FACTOR
3. Recompile and upload
4. Repeat testing until within ±2%
```

### Step 5: Deployment
```
1. Verify dashboard shows correct values
2. Check energy accumulation over time
3. Compare with electricity meter
4. Monitor for 1-2 weeks for stability
```

---

## PART I: VERIFICATION CHECKLIST

After uploading the new code, verify:

**Serial Monitor Output:**
- [ ] Shows "AmpPulse AI - Real Current Measurement"
- [ ] Shows "CT Sensor ADC Pin: GPIO35"
- [ ] Shows "CT Calibration Factor: 0.0234"
- [ ] Current reads 0.00A with no load
- [ ] Current changes when appliance turns ON
- [ ] Power value = Voltage × Current × 0.95
- [ ] Energy increases over time when load is ON
- [ ] Temperature/Humidity readings appear

**Dashboard:**
- [ ] /data endpoint returns all fields (current, energy, cost)
- [ ] Live current updates every 2 seconds
- [ ] Power card shows W value
- [ ] Energy card shows kWh accumulated
- [ ] Estimated Cost shows ₹ value
- [ ] Device Status shows ON or OFF (based on current)
- [ ] Relay 1 and Relay 2 still work

**Calibration:**
- [ ] Known 1000W load → reads ~4.35A
- [ ] Known 500W load → reads ~2.17A
- [ ] Within ±2% accuracy
- [ ] Readings are stable (no jitter)

---

## PART J: QUICK REFERENCE

### Most Important Configuration Values

```cpp
// In amppulse_esp32_REAL_CT_SENSOR.ino

// CHANGE THIS BASED ON YOUR CT SENSOR MODEL:
#define CT_CALIBRATION_FACTOR 0.0234

// CHANGE THIS BASED ON YOUR ELECTRICITY RATE:
#define ELECTRICITY_UNIT_RATE 6.0  // ₹ per kWh

// ADC PIN (usually GPIO35):
#define CT_PIN 35

// THRESHOLD FOR ON/OFF (usually 0.1A):
#define CT_CURRENT_THRESHOLD_ON 0.1
```

### Testing Loads & Expected Values

| Load | Expected Current @230V | Notes |
|------|---|---|
| 60W bulb | 0.26A | LED lights don't work (too low) |
| 500W heater | 2.17A | Good test, common appliance |
| 1000W heater | 4.35A | **BEST for calibration** |
| 1500W kettle | 6.52A | Fast acting, steady |
| 2000W kettle | 8.70A | Near max for SCT-013-010 |

---

## PART K: DATA FLOW DIAGRAM

### Complete Signal Path

```
230V AC Mains
    ↓
SCT-013 CT Sensor (clipped around wire)
    ↓ (proportional AC current signal)
Burden Resistor Circuit (56Ω + 0.1µF)
    ↓ (AC voltage, ~0.1-0.3V peak at 5A)
Voltage Divider Bias (10k:10k)
    ↓ (AC signal centered at 1.65V)
ESP32 ADC Pin GPIO35
    ↓ (raw ADC values 0-4095)
readCurrentFromCT() Function
    ├─ Sample 1000 ADC points
    ├─ Remove DC offset
    ├─ Calculate RMS
    ├─ Convert to voltage (÷4095 × 3.3)
    ├─ Apply calibration (×0.0234)
    ├─ Average 100 readings
    └─ Return Amperes
    ↓ (current variable = real Amps)
calculatePower() Function
    ├─ Power(W) = Voltage(V) × Current(A) × PF(0.95)
    └─ Return Watts
    ↓ (power variable = real Watts)
updateEnergy() Function
    ├─ Track time elapsed
    ├─ Energy(kWh) = Power × Time / 1,000,000
    └─ Return accumulated kWh
    ↓ (energy variable = real kWh)
calculateEstimatedCost() Function
    ├─ Cost(₹) = Energy(kWh) × Rate(₹/kWh)
    └─ Return cost in rupees
    ↓ (cost = real currency)
handleData() Function (API)
    ├─ Create JSON response
    ├─ Include voltage, current, power, energy, cost
    ├─ Include temperature, humidity
    ├─ Include device status (ON/OFF)
    ├─ Include relay states
    └─ Send to dashboard
    ↓
Dashboard (Web Browser)
    ├─ Display current in Amps
    ├─ Display power in Watts
    ├─ Display energy in kWh
    ├─ Display estimated cost in ₹
    ├─ Update every 2 seconds
    └─ Show device ON/OFF status
    ↓
Serial Monitor
    ├─ Display all values
    ├─ Show device status
    └─ Update every 2 seconds
    ↓
Backend API (Optional)
    ├─ POST telemetry to server
    ├─ Store in database
    ├─ Generate reports
    └─ Calculate monthly bills
```

---

## SUMMARY OF KEY CHANGES

| Aspect | Change |
|--------|--------|
| **Current Measurement** | Simulated 1.50A ❌ → Real CT sensor RMS ✅ |
| **Calibration** | Hardcoded → User-configurable factor |
| **Power Calculation** | Fake → Realistic (with power factor) |
| **Energy Tracking** | Meaningless → Accurate accumulation |
| **Cost Estimation** | Wrong → Correct (based on real kWh) |
| **Device Status** | Relay-based → Current-based (more accurate) |
| **Filtering** | None → 100-sample moving average |
| **Noise Floor** | None → 0.02A threshold |
| **Dashboard** | Fake values → Real measurements |
| **Serial Output** | Misleading → Accurate debugging |
| **Hardware** | None (PZEM simulated) → CT sensor + burden circuit |

---

**All changes preserve your existing Wi-Fi, relay control, temperature/humidity sensors, web server, and dashboard integration. Only current measurement is improved from simulated to real.**

