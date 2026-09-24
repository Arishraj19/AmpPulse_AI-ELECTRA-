# AmpPulse AI - SCT-013 CT Sensor Wiring & Calibration Guide

## SECTION 1: WIRING DIAGRAM

### Safe Interface Circuit Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  MAINS SUPPLY (230V AC)                                         │
└─────────────────────────────────────────────────────────────────┘
         │
         │
    ┌────┴────┐
    │          │
    │ SCT-013 │  ◄─── CT Clipped Around Active Conductor
    │ Core    │       (Wire carrying appliance current)
    │          │
    └────┬────┘
         │
  ┌──────┴──────┐
  │ Secondary   │
  │ Winding     │
  │ (2000:1)    │
  └──────┬──────┘
         │
    ┌────┴─────────────────────────────────────────────────────┐
    │ CT Secondary Terminals                                  │
    │ (Produces low current proportional to mains current)   │
    └────┬──────────────────────────────┬──────────────────────┘
         │                              │
         │                              │
    ┌────▼───┐                    ┌────▼────┐
    │ Pin A  │                    │ Pin B   │
    └────┬───┘                    └────┬────┘
         │                             │
         │  [56Ω Burden Resistor]      │
         │  (Converts current to Vot)  │
         │                             │
    ┌────┴─────────────────────────────┴────┐
    │          Burden Circuit                │
    │                                        │
    │   ┌──────[56Ω]──────┐                │
    │   │                 │                │
    │  (+)               (-)               │
    │   │                 │                │
    │   ├─────[10µF]──────┤  ◄── AC Coupling Capacitor
    │   │                 │       (Blocks DC, passes AC)
    │   │                 │                │
    │   ├────[10kΩ]───[10kΩ]──┐          │
    │   │      │          │    │          │
    │  Vcc   GND        GND   │          │
    │ (3.3V)                  │          │
    │   │                     │          │
    │   └─────────┬───────────┘          │
    │             │                      │
    │         (Bias Voltage = 1.65V)     │
    │             │                      │
    │             ├──────────[1kΩ]───────┤
    │             │                      │
    │            ADC Pin (GPIO35)        │
    │                                    │
    └────────────────────────────────────┘

╔════════════════════════════════════════════════════════╗
║         ESP32 CONNECTIONS - PIN DIAGRAM               ║
╠════════════════════════════════════════════════════════╣
║                                                        ║
║  CT Sensor ADC ──────────> GPIO 35 (ADC7)             ║
║  Ground ─────────────────> GND (Any GND pin)          ║
║  Vcc (3.3V) ─────────────> 3.3V pin                   ║
║                                                        ║
║  Optional Voltage Divider Bias:                       ║
║  3.3V ──[10kΩ]──┬──[10kΩ]── GND                       ║
║               GPIO35                                  ║
║                                                        ║
╚════════════════════════════════════════════════════════╝
```

### Physical Component Layout

```
┌─────────────────────────────────────────────────────────────┐
│ Breadboard Layout (Simple Setup)                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Left Side (Power):          Right Side (Signal):           │
│  Row 1: ──────Vcc(3.3V)      Row 1: ──────CT_A             │
│  Row 2: ──────GND            Row 2: ──────[56Ω]────GND    │
│                              Row 3: ──────CT_B(to 56Ω)     │
│ Voltage Divider:            Row 4: ──────[10µF]────GND    │
│  Row 3: ──────[10kΩ]────     Row 5: ──────GPIO35           │
│         │              │     Row 6: ──────(from cap)       │
│         ├──────GND  GPIO35                                 │
│         │                                                   │
│        [10kΩ]                                              │
│         │                                                   │
│  Row 4: ──────GND                                          │
│                                                             │
│ Signal Path:                                               │
│ CT Sensor ──[56Ω]──[10µF]──┬──GPIO35                      │
│                            │                              │
│                        (Bias from V-divider)              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Minimal Wiring (Simplest Setup)

If you don't have a voltage divider, use this simpler version:

```
CT Pin A ──[56Ω]──┬──[10µF Capacitor]──┬── GND
                  │                     │
             To ESP32 GPIO35            └── (Center of AC waveform)
                  
CT Pin B ────────────────────────────────── GND

This is simpler but less stable. The voltage divider is recommended.
```

## SECTION 2: COMPONENT BILL OF MATERIALS

| Component | Value | Qty | Purpose |
|-----------|-------|-----|---------|
| CT Sensor | SCT-013-010 | 1 | Current measurement |
| Burden Resistor | 56Ω 1/2W | 1 | Convert current to voltage |
| Capacitor | 0.1µF 250V (ceramic) | 1 | AC coupling (block DC) |
| Resistor | 10kΩ 1/4W | 2 | Voltage divider (bias to 1.65V) |
| Resistor | 1kΩ 1/4W | 1 | Impedance for ADC |
| Jumper Wires | 22AWG | ~10 | Breadboard connections |
| Breadboard | Full-size | 1 | Testing/prototyping |
| ESP32 | WROOM-DA | 1 | Main controller |

**TOTAL ESTIMATED COST: ₹150-200**

## SECTION 3: STEP-BY-STEP WIRING INSTRUCTIONS

### Step 1: Prepare the Burden Resistor Circuit

```
On Breadboard:

1. Insert 56Ω resistor between row 10 and row 20
   ├─ Resistor pin A: Row 10, Column A
   └─ Resistor pin B: Row 20, Column A

2. Insert 0.1µF capacitor
   ├─ Capacitor (+): Row 20, Column B (same as resistor pin B)
   └─ Capacitor (-): Row 20, Column C → Connect to GND bus

3. Connect GND bus
   ├─ Row 20, Column C → GND (Blue line on breadboard)
   └─ Multiple GND jumpers to provide sufficient ground returns
```

### Step 2: Connect CT Sensor Secondary

```
CT Sensor Terminals:
├─ Pin A (Primary coil side A) → Breadboard Row 10, Column A (with 56Ω resistor)
└─ Pin B (Primary coil side B) → GND or Breadboard Row 20, Column C (with capacitor)

Note: The CT sensor secondary output is proportional to primary current.
The burden resistor converts this current to a voltage measurable by ADC.
```

### Step 3: Voltage Divider (Optional but Recommended)

```
Purpose: Bias the AC signal to the center of ADC range (1.65V)

Setup:
3.3V ──[10kΩ]──┬── Row 30, Column D (call this BIAS_POINT)
              │
              ├──[10kΩ]── GND

Connect:
- 3.3V pin from ESP32 → First 10kΩ resistor top
- GND pin from ESP32 → Second 10kΩ resistor bottom
- Center junction (BIAS_POINT) → Breadboard Row 30, Column D
- BIAS_POINT → 1kΩ resistor → Row 35, Column E (GPIO35)
```

### Step 4: Connect ADC Pin

```
From capacitor center (Row 20, Column B):
├─ Connect to row 35, Column E (GPIO35 input line)
│
└─ This is where the AC signal from CT sensor arrives at ESP32

From voltage divider bias (Row 30, Column D):
├─ Connect 1kΩ resistor
│
└─ Connect other end to Row 35, Column E (GPIO35 same point)

Result: GPIO35 receives:
- AC signal (0.1-0.3V peak) centered at 1.65V
- Bias from voltage divider keeps ADC in linear range
```

### Step 5: Connect to ESP32

```
Breadboard to ESP32 Headers:

GND Breadboard ──────────> ESP32 GND (any pin)
Vcc (3.3V) Breadboard ───> ESP32 3.3V pin
GPIO35 Signal ───────────> ESP32 GPIO35 (ADC input)

Required Jumpers:
- Red: 3.3V power (from ESP32 to Vcc rail on breadboard)
- Black: GND (from ESP32 to GND rail on breadboard)
- Green/Yellow: Signal line (GPIO35)
```

### Step 6: Clip CT Sensor Around Mains Wire

```
SAFETY: 
- Do NOT open the CT core - mains wire stays OUTSIDE
- Clip the plastic core around the active conductor
- Ensure magnetic core closes completely

Physical Placement:
1. Choose the wire to measure (single phase appliance wire)
2. Open CT sensor core gently
3. Thread mains wire through the core
4. Close core until it clicks (magnetic latch)
5. Check that wire is centered in the core
6. Verify no air gaps in the core closure
```

## SECTION 4: CALIBRATION STEP-BY-STEP

### Pre-Calibration Checklist

Before calibrating, verify:

- [ ] CT sensor secondary pins connected to burden circuit
- [ ] Burden resistor (56Ω) in place
- [ ] Capacitor (0.1µF) connected for AC coupling
- [ ] Voltage divider (10k+10k) properly biased
- [ ] GPIO35 receives the AC signal
- [ ] ESP32 programmed with updated code
- [ ] Serial monitor accessible at 115200 baud
- [ ] Wi-Fi connection working
- [ ] Web dashboard accessible

### Phase 1: Zero-Current Baseline

**Objective**: Verify the system reads ~0.00A with no load

```
Procedure:
1. Disconnect all appliances from the circuit being monitored
2. Power up ESP32
3. Wait 10 seconds for stabilization
4. Open Serial Monitor
5. Observe readings every 2 seconds
6. Expected: Current = 0.00A (with minimal noise < ±0.01A)

Result Interpretation:
✓ If current is 0.00A ± 0.01A  → Proceed to Phase 2
✗ If current is > 0.05A         → Check for noise sources
✗ If current drifts constantly  → Check voltage divider bias
✗ If reading is unstable        → Increase AVERAGING_SAMPLES
```

**What to do if zero baseline is noisy:**

```cpp
// In the code, increase averaging:
#define CT_AVERAGING_SAMPLES 200  // Increase from 100 to 200

// This smooths out electrical noise and AC ripple
```

### Phase 2: Known Load Test

**Objective**: Establish calibration factor using a reference load

**Equipment Required:**
- Resistive load with known power rating (examples below)
- AC clamp meter or multimeter with current measurement
- Resistance must be PURELY RESISTIVE (no motor/inductive loads)

**Recommended Test Loads:**

| Appliance | Power | Expected Current @ 230V |
|-----------|-------|------------------------|
| Incandescent Bulb | 60W | 0.26A |
| Electric Heater | 500W | 2.17A |
| Room Heater | 1000W | 4.35A |
| Electric Kettle | 1500W | 6.52A |
| Water Heater | 2000W | 8.70A |

**Procedure (Using 1000W Heater):**

```
Step 1: Safety Check
  □ Ensure all connections are secure
  □ Verify CT core is closed properly
  □ Check that mains wire is centered in core

Step 2: Power Up
  □ Turn on ESP32
  □ Wait 10 seconds for stabilization
  □ Open Serial Monitor (Tools → Serial Monitor, 115200 baud)

Step 3: Baseline Reading (No Load)
  □ Ensure 1000W appliance is OFF
  □ Record Serial Monitor output for 30 seconds
  □ Note current reading (should be ~0.00A)
  □ Record as: BASELINE_CURRENT

Step 4: Turn On Known Load
  □ Turn on 1000W heater/toaster
  □ Let it stabilize for 30 seconds
  □ Watch Serial Monitor for stable current reading
  □ Record as: ESP32_CURRENT (e.g., 4.20A)

Step 5: Measure with Reference Meter
  □ Use AC clamp meter to measure actual current
  □ Clamp around the SAME wire as CT sensor
  □ Wait for reading to stabilize
  □ Record as: MULTIMETER_CURRENT (e.g., 4.35A)

Step 6: Calculate Calibration Adjustment
  
  Measurement Error Ratio = MULTIMETER_CURRENT / ESP32_CURRENT
                          = 4.35 / 4.20
                          = 1.0357 (3.57% error, acceptable)

  New Calibration Factor = OLD_CALIBRATION × Error_Ratio
                         = 0.0234 × 1.0357
                         = 0.02424

Step 7: Update Code
  Locate in Arduino code:
  #define CT_CALIBRATION_FACTOR 0.0234
  
  Change to:
  #define CT_CALIBRATION_FACTOR 0.02424
  
  Recompile and upload to ESP32

Step 8: Repeat Test
  □ Verify new calibration is more accurate
  □ Record new ESP32 reading for 1000W heater
  □ Should now be closer to 4.35A
```

### Phase 3: Multi-Point Calibration (More Accurate)

**Objective**: Verify calibration across multiple load levels

```
Test Points:
1. 500W Load
   Expected: 2.17A
   Record ESP32 reading: _____
   
2. 1000W Load
   Expected: 4.35A
   Record ESP32 reading: _____
   
3. 1500W Load
   Expected: 6.52A
   Record ESP32 reading: _____

Analysis:
If all three points are within ±2% of expected values,
your calibration factor is acceptable.

If one point is significantly off:
- Check if load is actually resistive (not motor)
- Verify CT sensor is properly clipped
- Check for noise in electrical supply
```

**Calibration Accuracy Target:**

```
Acceptable Range: Measured ± 2% of Expected
Better:          Measured ± 1% of Expected
Excellent:       Measured ± 0.5% of Expected

Examples:
Expected 4.35A:
  ✓ 4.25A - 4.45A (±2.3%)    : Acceptable
  ✓ 4.29A - 4.41A (±1.4%)    : Better
  ✓ 4.33A - 4.37A (±0.5%)    : Excellent
```

### Phase 4: Real-World Load Testing

**Objective**: Verify system works with actual appliances

```
Test Procedure:
1. Turn on various household appliances one by one
2. Observe ESP32 current reading
3. Mentally estimate if reading is reasonable

Examples:

Ceiling Fan (60W):
  Estimated: 60W ÷ 230V = 0.26A
  ESP32 shows: ~0.25-0.27A ✓

Color TV (80W):
  Estimated: 80W ÷ 230V = 0.35A
  ESP32 shows: ~0.34-0.36A ✓

Refrigerator (~150W average):
  Estimated: 150W ÷ 230V = 0.65A
  ESP32 shows: ~0.60-0.70A (compressor cycles) ✓

Microwave (1000W):
  Estimated: 1000W ÷ 230V = 4.35A
  ESP32 shows: ~4.30-4.40A ✓
```

## SECTION 5: TROUBLESHOOTING CALIBRATION ISSUES

| Symptom | Possible Cause | Solution |
|---------|---|---|
| Current always 0.00A even with load ON | CT not clipped properly | Re-clip CT, ensure wire is through core center |
| Reading is consistently HIGH (e.g., 5.0A instead of 4.35A) | Calibration factor too large | Decrease CT_CALIBRATION_FACTOR by 10-15% |
| Reading is consistently LOW (e.g., 3.5A instead of 4.35A) | Calibration factor too small | Increase CT_CALIBRATION_FACTOR by 10-15% |
| Reading jumps around (unstable) | Electrical noise or insufficient filtering | Increase CT_AVERAGING_SAMPLES to 200-300 |
| Reading doesn't change when load changes | ADC pin not connected properly | Check GPIO35 connections, verify jumper wire |
| Reading freezes at zero | ADC input floating or clipped | Check burden resistor connection, verify capacitor |
| Baseline (no-load) reading is > 0.1A | DC offset issue | Check voltage divider, ensure balanced bias |

## SECTION 6: FINAL VERIFICATION CHECKLIST

```
□ Zero baseline test: Current reads 0.00A with no load
□ 1000W reference load: Current reads within ±2% of expected
□ Serial monitor shows stable readings without jitter
□ Dashboard web page displays current in real-time
□ Power calculation (W = V × A) makes sense
□ Energy accumulation increases over time when load is ON
□ Device status changes to ON when current > 0.1A
□ Temperature and humidity readings are reasonable
□ Relay control still works (turns appliance ON/OFF)
□ Wi-Fi connection is stable
□ Backend integration working (if enabled)

When all boxes are checked: ✓ System is ready for deployment!
```

## SECTION 7: LONG-TERM MAINTENANCE

### Monthly Verification

```
Procedure:
1. Pick a day each month
2. Turn on a known 1000W load for 1 minute
3. Note ESP32 reading
4. Compare to previous months
5. If reading drifts > 5%, recalibrate

Expected: Should remain stable within ±2%
```

### Annual Calibration

```
Every 12 months, perform full calibration procedure
(Phase 1-4) to maintain accuracy.

Reason: Component aging, temperature drift, burden
        resistor tolerance changes can affect accuracy
        over time.
```

### Component Replacement

If CT sensor is replaced or burden circuit is modified:
1. Perform full calibration from scratch
2. Do NOT assume previous calibration factor applies
3. New burden resistor tolerance can significantly affect readings

---

**End of Wiring and Calibration Guide**
