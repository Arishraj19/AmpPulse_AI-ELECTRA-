# AmpPulse AI - CT Sensor (SCT-013) Integration Guide

## A. ANALYSIS OF EXISTING CODE

### What Was Found:
1. **Simulated Current Function** (`readCurrent()` lines 212-225):
   - Returns hardcoded 1.50 A when ANY relay is ON
   - Returns 0.00 A when both relays are OFF
   - **NOT based on any real sensor measurement**

2. **Impact on System**:
   - All power calculations (W/kW) are inaccurate
   - Energy consumption tracking is meaningless
   - Electricity bill estimates are false
   - Device ON/OFF status relies only on relay state, not actual power draw

3. **Working Components** (Preserved):
   - ZMPT101B voltage sensor (real, calibrated)
   - DHT22 temperature/humidity (real)
   - 2-channel relay control (real)
   - Web server, Wi-Fi, dashboard communication (all intact)
   - Status LED indication
   - Serial monitor logging

### Hardware Comments in Code:
```cpp
// Line 11: "PZEM-004T Current: SIMULATED for now"
// Lines 211-220: Full comment block explaining simulation
```

---

## B. CODE REMOVED / REPLACED

### Removed Function:
```cpp
// =====================================================
// Simulated PZEM Current [REMOVED]
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

### Replaced With:
- Real CT sensor (SCT-013) RMS current calculation
- Proper ADC sampling and signal processing
- Calibration factor management
- Device status detection logic
- Filtering/averaging for stability

---

## C. HARDWARE REQUIREMENTS

### SCT-013 Current Sensor Options:
| Model | Max Current | Primary Circuit |
|-------|------------|-----------------|
| SCT-013-005 | 5 A | Low-current circuits |
| SCT-013-010 | 10 A | Standard circuits |
| SCT-013-020 | 20 A | Standard circuits |
| SCT-013-030 | 30 A | Heavy loads |

### Safe Interface Circuit (SCT-013 → ESP32)

```
230V AC Mains
    │
    └──[CT Sensor Core]──────────┐
                                 │
                    ┌────────────┴─────────────┐
                    │                          │
                   [R]                       [R]
                    │                          │
              [Load Resistor]           [Burden Resistor]
              (typically 150-180Ω)      (typically 56Ω)
                    │                          │
                    ├────────────┬─────────────┤
                    │            │             │
                  GND          [C]           Vcc(+3.3V)
                              Capacitor
                           (0.1µF - 10µF)
                                 │
                            ESP32 ADC Pin
                            (GPIO 35 or 34)
```

### Burden Resistor Calculation:
```
For SCT-013-010:
- Turns Ratio (n) = 2000:1
- Max Primary Current = 10 A
- Load impedance at secondary = 10/2000 = 0.005 A (5 mA)
- For 1V peak output: R = 1V / 0.005A = 200Ω

Practical burden resistor = 56-180Ω (depends on desired sensitivity)
- 56Ω → ~0.28V peak at 5A
- 180Ω → ~0.9V peak at 5A

Our circuit uses 56Ω + 0.1µF capacitor for filtering
```

### Wiring Diagram (Simplified):

```
SCT-013-010
├─ Secondary Out (Pin A) ──[56Ω Burden]──[0.1µF Cap]── GND
└─ Secondary Out (Pin B) ──────────────────────────────┬─ GND
                                                       └─ ADC Pin (GPIO 35)

Ground Reference:
ESP32 GND ── Mains GND (if available) or isolated GND plane
```

### SAFETY CRITICAL:
- **NEVER connect 230V AC directly to ESP32 ADC**
- **CT sensor MUST have burden circuit before feeding to ADC**
- **Capacitor MUST be present to block DC offset**
- **Load resistor provides impedance for output waveform**
- **Use 10kΩ resistor divider to bias AC signal to 1.65V (mid-ADC range)**

---

## D. CALIBRATION FACTOR DETERMINATION

### What is Calibration Factor?
The calibration factor converts the RMS ADC reading to actual Amperes:

```
Actual Current (A) = RMS_ADC × Calibration_Factor
```

### Step-by-Step Calibration:

#### 1. **Theoretical Calculation** (Starting Point):
```cpp
// For SCT-013-010 with 56Ω burden resistor:
//
// Secondary current at 10A primary = 10A / 2000 = 0.005A (5mA)
// Voltage across 56Ω = 0.005A × 56Ω = 0.28V peak
// RMS voltage = 0.28 / 1.414 = 0.198V RMS
//
// If we bias the signal to 1.65V center with a 10k:10k divider:
// ADC reading at 0A = ~2048 (12-bit, midpoint)
// ADC reading at 5A = ~2048 + (0.198V * ADC_scale)
//
// ADC_scale at 11dB attenuation = 4095 / 3.3V = 1240.9
// Voltage = ADC_reading × (3.3V / 4095) = ADC_reading × 0.00081
//
// Calibration_Factor (starting) ≈ 10A / (RMS_ADC_at_10A - RMS_ADC_at_0A)
//
// Typically: 0.02 to 0.04 (adjust based on testing)
```

#### 2. **Practical Calibration** (Recommended):

**Equipment Needed:**
- Known resistive load (e.g., 1000W toaster, kettle, heater)
- AC multimeter (RMS current capability)
- Laptop with serial monitor open

**Procedure:**

```
Step 1: Connect CT sensor properly (burden circuit + ADC pin)
Step 2: Open Serial Monitor at 115200 baud
Step 3: Let ESP32 stabilize for 10 seconds
Step 4: Plug in KNOWN LOAD (e.g., 1000W appliance)
        1000W ÷ 230V = ~4.3A (theoretical)
Step 5: Read SERIAL OUTPUT:
        Current: X.XX A
Step 6: Measure ACTUAL current with multimeter clamp meter
        Let's say it reads 4.35 A
Step 7: Calculate adjustment:
        Measured_ESP32 / Actual_Multimeter = 4.3 / 4.35 ≈ 0.988
        This means our calibration is very close!
Step 8: If very different:
        - If ESP32 reads HIGH: increase CALIBRATION constant
        - If ESP32 reads LOW: decrease CALIBRATION constant
Step 9: Adjustment formula:
        New_Calibration = Old_Calibration × (Actual / ESP32_Reading)
Step 10: Update code and repeat until within ±2% accuracy
```

#### 3. **Fine-Tuning**:

```cpp
// In the code, calibration factor is here:
#define CT_CALIBRATION_FACTOR 0.0234  // ADJUST THIS VALUE

// Test with different loads:
// - 500W load (should show ~2.2A at 230V)
// - 1000W load (should show ~4.3A at 230V)
// - 1500W load (should show ~6.5A at 230V)
// - 2000W load (should show ~8.7A at 230V)

// Record results and average the calibration error
// Fine-tune CALIBRATION constant accordingly
```

---

## E. COMPLETE DATA FLOW

```
SCT-013 CT Sensor (Clipped around mains wire)
    ↓ (Analog AC signal ~0.1-0.3V RMS at 5A)
Burden Resistor Circuit (56Ω + 0.1µF capacitor)
    ↓ (AC waveform isolated and scaled)
ESP32 ADC Pin 35 (GPIO35)
    ↓ (1000 samples at 200µs intervals)
RMS Calculation (remove DC offset, compute root-mean-square)
    ↓ (RMS_ADC value)
Apply Calibration Factor (×0.0234)
    ↓ (Actual Amperes)
Update 'current' variable
    ↓
Power Calculation: W = V × A × PF (Power Factor = 0.95)
    ↓
Energy Tracking: kWh = (W × time) / 1,000,000
    ↓
Cost Estimation: ₹ = kWh × unit_rate (e.g., ₹6 per kWh)
    ↓
Device Status: if (current > 0.1A) → ON else OFF
    ↓
JSON API Response (/data endpoint)
    ↓
Dashboard Display + Serial Monitor Output
    ↓
Backend API (if telemetry enabled)
```

---

## F. CONFIGURATION CHECKLIST

Before uploading code:

- [ ] **CT Sensor ADC Pin**: Set to GPIO 35 (or 34 if using 35 for something else)
- [ ] **CT Calibration Factor**: Start with 0.0234 (adjust after testing)
- [ ] **CT Model**: SCT-013-010 (change if using different model)
- [ ] **Burden Resistor**: 56Ω (verify in your circuit)
- [ ] **Voltage Nominal**: 230V (India standard; adjust if different region)
- [ ] **Power Factor**: 0.95 (typical for resistive loads; adjust if known)
- [ ] **Current Threshold for ON/OFF**: 0.1A (appliance is considered ON if > 0.1A)
- [ ] **Averaging Samples**: 100 (for stable readings)
- [ ] **ZMPT Calibration**: 0.325 (keep existing voltage calibration)

---

## G. TESTING & VERIFICATION PROCEDURE

### Phase 1: Hardware Check
```
1. Disconnect mains power
2. Check CT sensor secondary output pins
3. Verify burden resistor is connected (56Ω)
4. Check capacitor (0.1µF) is in place
5. Verify ADC pin (GPIO35) is connected
6. No loose wires
7. All connections soldered properly
```

### Phase 2: Power-Up Test
```
1. Connect ESP32 to laptop via USB
2. Open Arduino IDE Serial Monitor (115200 baud)
3. Reset ESP32
4. Wait for Wi-Fi connection (look for "Wi-Fi connected!" message)
5. Check initial readings:
   - Voltage should show ~220-240V (if mains is live)
   - Current should show ~0.00A (no load)
   - Temperature and humidity should be reasonable
6. Allow 30 seconds of stable output
```

### Phase 3: Load Testing
```
Test 1: No Load
  - CT sensor NOT clipped to any wire
  - Expected: Current = 0.00 A
  - Expected: Device Status = OFF
  - Duration: 30 seconds
  - Record: Any noise/drift?

Test 2: Known Load (Incandescent Bulb 60W)
  - Clip CT around bulb's mains wire
  - Turn on bulb
  - Expected: Current = 60W ÷ 230V = ~0.26A
  - Expected: Device Status = ON
  - Duration: 2 minutes
  - Check: Is value stable? Any fluctuation?

Test 3: Medium Load (1000W Toaster/Heater)
  - Clip CT around appliance's mains wire
  - Turn on appliance
  - Expected: Current = 1000W ÷ 230V = ~4.35A
  - Expected: Device Status = ON
  - Check with multimeter: Record actual reading
  - Duration: 5 minutes
  - Calculate calibration adjustment if needed

Test 4: Heavy Load (2000W)
  - Clip CT around 2000W appliance
  - Turn on
  - Expected: Current = 2000W ÷ 230V = ~8.7A
  - Expected: Device Status = ON
  - Check for ADC saturation (max ~10A for SCT-013-010)
  - Duration: 5 minutes

Test 5: Relay Control + CT Sensor
  - Clip CT around relay 1's load
  - Press "Relay 1 ON" on dashboard
  - Verify CT detects current
  - Press "Relay 1 OFF"
  - Verify CT drops to 0.00A
  - Duration: 1 minute
```

### Phase 4: Calibration Refinement
```
1. Run Test 3 again with known 1000W load
2. Note ESP32 reading (e.g., 4.20A)
3. Note multimeter reading (e.g., 4.35A)
4. Calculate error: 4.20 ÷ 4.35 = 0.965 (3.5% low)
5. Adjustment: New_Cal = 0.0234 × (4.35 ÷ 4.20) = 0.0243
6. Update #define CT_CALIBRATION_FACTOR 0.0243
7. Recompile and upload
8. Repeat Test 3
9. Continue until within ±2% accuracy
```

### Phase 5: Dashboard Verification
```
1. Open dashboard at http://<ESP32-IP>
2. Add ESP32 IP in "📡 ESP32 Connect" view
3. Monitor live readings:
   - Voltage card
   - Current card
   - Power card
   - Temperature card
   - Humidity card
4. Toggle Relay 1 ON
5. Verify Power = Voltage × Current
6. Check device status changes
7. Toggle Relay 1 OFF
8. All readings should return to baseline
```

### Phase 6: Serial Monitor Output Example
```
Expected Serial Output:
================================
Voltage     : 231.2 V
Current     : 4.32 A
Power       : 998.8 W
Temperature : 28.5 C
Humidity    : 65.3 %
Relay 1     : ON
Relay 2     : OFF
Device Status: ON (Current > 0.1A threshold)
================================
```

---

## H. TROUBLESHOOTING

| Issue | Cause | Solution |
|-------|-------|----------|
| Current always 0.00A | CT not clipped to wire | Clip CT around active conductor |
| Current reads too HIGH | Calibration factor too large | Decrease CT_CALIBRATION_FACTOR |
| Current reads too LOW | Calibration factor too small | Increase CT_CALIBRATION_FACTOR |
| Unstable/jittery readings | Insufficient filtering | Increase AVERAGING_SAMPLES to 200 |
| Voltage shows 0V | ZMPT101B not reading | Check ZMPT_PIN connection |
| ADC clips/maxes out | Load exceeds CT range | Use SCT-013-030 for higher currents |
| No Wi-Fi connection | Credentials wrong | Check WIFI_SSID and WIFI_PASSWORD |
| Dashboard won't connect | Firewall/CORS issue | Ensure CORS headers present (already in code) |

---

## I. NEXT STEPS

1. ✅ **Upload updated Arduino code** with CT sensor integration
2. ✅ **Wire CT sensor** with burden circuit to ESP32 ADC
3. ✅ **Test with known loads** (follow Phase 1-6 above)
4. ✅ **Calibrate** using 1000W reference load
5. ✅ **Verify dashboard** shows correct values
6. ✅ **Enable backend telemetry** (optional) for analytics
7. ✅ **Monitor energy usage** and compare with electricity meter

---

## REFERENCES

- **SCT-013 Datasheet**: https://www.openenergymonitor.org/
- **CT Sensor Safety**: https://www.sparkfun.com/products/11005
- **ESP32 ADC**: https://docs.espressif.com/projects/esp-idf/en/latest/
- **RMS Calculation**: https://en.wikipedia.org/wiki/Root_mean_square

