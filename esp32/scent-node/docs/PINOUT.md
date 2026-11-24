# Scent / IAQ node - ESP32 pinout

Board: ESP32-WROOM-32 DevKit (USB-C, CP2102). Pin numbers below are **GPIO
numbers** (the "Dxx"/"IOxx" labels on the board), not physical pin positions.
`include/config.h` is the source of truth for the firmware; keep this file in
sync with it.

## Pin map

| GPIO | Use | Direction | Status | Notes |
|---|---|---|---|---|
| 25 | Lavender diffuser A | out | **in firmware** | MOSFET gate |
| 26 | Lavender diffuser B | out | **in firmware** | MOSFET gate |
| 27 | Pine diffuser A | out | **in firmware** | MOSFET gate |
| 4 | Pine diffuser B | out | **in firmware** | MOSFET gate (moved off 13 to keep JTAG free) |
| 32 | Citrus diffuser A | out | **in firmware** | MOSFET gate |
| 33 | Citrus diffuser B | out | **in firmware** | MOSFET gate |
| 21 | I2C SDA | i/o | **in firmware** | BME688 now; CO2 sensor later, same bus |
| 22 | I2C SCL | out | **in firmware** | |
| 2 | Status LED | out | **in firmware** | On-board LED: solid = MQTT up, blink = offline |
| 16 | Master kill Q1 (USB splitter power) | out | **in firmware** | Rev A carrier; HIGH = diffusers powered |
| 17, 19 | UART2 TX / RX (PM2.5 sensor) | i/o | reserved | e.g. PMS5003; RX moved off 16 (kill switch) |
| 18 | Ventilation fan PWM | out | reserved | 25 kHz LEDC, 4-pin PWM fan |
| 34 | Ventilation fan tach | in | reserved | Input-only; needs external 10k pull-up to 3.3 V |
| 35, 36 (VP), 39 (VN) | Scent reservoir level sensors | in | reserved | Input-only, no internal pull-ups |
| 23 | Spare digital | i/o | free | Safe general-purpose pin |
| 12, 13, 14, 15 | JTAG (ESP-Prog debugger) | - | keep free | 12 and 15 are also boot-strapping pins |

### Never use

| GPIO | Why |
|---|---|
| 0 | BOOT button / strapping: must be high at reset or the board won't run |
| 1, 3 | UART0 TX/RX: USB serial (uploads + Serial Monitor) |
| 5 | Strapping pin: outputs a signal at boot |
| 6-11 | Wired to the on-module flash; touching them crashes the chip |
| 12 | Strapping (flash voltage): pulled high at boot = boot failure |

## Wiring

### Diffusers (x6) - low-side N-MOSFET switch

The ESP32 runs at 3.3 V and can only supply about 20 mA per pin, so it can't
power an atomizer directly. Each GPIO switches a MOSFET, and the MOSFET
switches the atomizer's ground.

```
            +5 V supply (separate, >= 2 A)
                 |
            [ atomizer + ]
            [  module    ]
            [ atomizer - ]
                 |
                 D
GPIO --100R--+-- G   N-MOSFET (logic-level, e.g. AO3400A or a D4184 module)
             |   S
            10k  |
             |   |
GND ---------+---+---- common GND (5 V supply GND tied to ESP32 GND)
```

- **MOSFET must be logic-level**: fully on at **Vgs = 3.3 V**. Check the
  datasheet's Rds(on) at Vgs <= 3.3 V. AO3400A or ready-made D4184 modules
  work; IRF540/IRFZ44 (non-"L") do not.
- **10k gate-to-ground pull-down** keeps each diffuser off while the ESP32
  boots or resets. The firmware also forces every output low first thing.
- **100 R gate resistor** limits the inrush current into the gate (optional on
  modules that already have one).
- USB atomizer modules: use a USB-A female breakout, or cut the cable. Red =
  +5 V, black = GND.
- Load: about 0.3-0.5 A per atomizer; at most 2 run at once (one scent, A+B),
  so a **5 V / 2 A** supply leaves headroom. Add a 470-1000 uF capacitor across
  the 5 V rail near the modules.
- **Check before wiring:** some modules only mist after a button press. If
  yours do, the MOSFET (or an optocoupler) has to "press" the button instead,
  and the firmware needs a pulse mode.

### BME688 (I2C)

| BME688 breakout | ESP32 |
|---|---|
| VIN / 3V3 | 3V3 |
| GND | GND |
| SDA / SDI | GPIO 21 |
| SCL / SCK | GPIO 22 |
| SDO | leave open (address 0x77) or GND (0x76; change `kBmeAddress`) |
| CS | leave open (keeps it in I2C mode) |

Most breakouts include I2C pull-ups. If you build your own, add 4.7k from SDA
and SCL to 3.3 V. Mount the sensor in the airflow, away from the atomizer
outlets and the ESP32 (both warm it up).

### Reserved: future IAQ sensors (client's future-iteration list)

- **CO2** (e.g. Sensirion SCD41, I2C 0x62): same I2C bus, GPIO 21/22.
- **PM2.5** (e.g. Plantower PMS5003, 5 V power, 3.3 V UART): sensor TX -> GPIO 19,
  sensor RX -> GPIO 17 (GPIO 16 is the master kill switch).
- **Exhaust/ventilation fan** (4-pin PWM): PWM -> GPIO 18 through a transistor or
  open-drain buffer; tach -> GPIO 34 with a 10k pull-up to 3.3 V; 12 V fan power
  from its own supply, grounds tied together.

## Power

- Bench: USB-C powers the ESP32; the atomizers still need their own 5 V supply.
- In the pod: one 5 V / 3 A supply can feed both. ESP32 **VIN (5V)** pin plus
  the atomizer rail; keep the atomizer wiring short and add the capacitor.
- Never power the atomizers from the DevKit's 5V pin while on USB: the board's
  USB path isn't rated for it.

## Checking the wiring

With the board on USB, open the Serial Monitor and use the bench console:

```
pin lavender 1    # diffuser A of lavender on for 3 s - should mist
pin lavender 2
pin pine 1        ... and so on for all six
sensor            # BME688 reading; "NOT FOUND" = check SDA/SCL/power/address
```
