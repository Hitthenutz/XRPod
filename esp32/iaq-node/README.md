# IAQ node: the BME688 on its own ESP32

Reads the BME688 (temperature, humidity, pressure, air quality) every 3 s and
sends it to the Pi on `xrpod/iaq/reading`, where `pi/scent.py` already
listens. It's separate from the scent node so the scent firmware doesn't
change. It only reports; it has no outputs.

## 1. Wiring

Any ESP32 WROOM-32 DevKit. It can sit on the same breadboard as the scent
ESP32, as long as each board keeps its own 3V3:

| BME688 | IAQ ESP32 |
|---|---|
| VIN / 3V3 / VCC | **3V3** of *this* ESP32 (never 5V / VIN) |
| GND | **GND** |
| SDA (or SDI) | **GPIO 21** (label D21 / G21) |
| SCL (or SCK) | **GPIO 22** (label D22 / G22) |

Leave SDO, CS and INT unconnected. Sharing GND between the two ESP32s is
fine; **never connect one ESP32's 3V3 to the other's**. Both boards are
powered over their own USB.

If the sensor's pins aren't soldered, press the header in firmly (slightly
tilted) or the readings will come and go.

## 2. Flash it

1. VS Code with the **PlatformIO IDE** extension.
2. **File > Open Folder** > `esp32/iaq-node`. Wait for PlatformIO to finish
   setting up (first time only, a few minutes).
3. Plug in the IAQ ESP32. If the scent ESP32 is plugged in too, unplug it
   for now, or set `upload_port` in `platformio.ini`, so the right board gets
   flashed.
4. Click **Upload** (right arrow, bottom bar). If it stalls at
   "Connecting...", hold the board's **BOOT** button until it starts.
5. Click **Serial Monitor** (plug icon).

## 3. What you should see

```
XRPod IAQ node (BME688) booting
[i2c] scanning SDA=GPIO21 SCL=GPIO22 ...
[i2c]   device at 0x77  <- BME688?
[iaq] BME688 found at 0x77 - a reading every 3 s
[net] no include/secrets.h - offline: readings are only printed here
{"temp_c":22.5,"humidity_pct":41.2,"pressure_hpa":1013.3,"gas_kohm":85.3,...}
```

Breathe on the sensor: humidity goes up within a few readings. The gas value
takes a few minutes to settle after power-up (`baseline_ready` turns true
after about a minute of clean air).

| You see | Fix |
|---|---|
| `[i2c] nothing found` | Check 3V3, GND, SDA on 21, SCL on 22, and that the pins really touch |
| A device, but `BME688 not found` | A different chip at that address: check it's the BME688 board |
| Readings, then `stopped answering` | Loose pins: press them in or solder them |
| Fast-blinking blue LED | No sensor; slow blink = no Pi; solid = sending to the Pi |

## 4. Send readings to the Pi

1. Copy `include/secrets.example.h` to `include/secrets.h` (git-ignored,
   never committed).
2. Fill in the Pi hotspot's Wi-Fi name and password, and the MQTT login.
   Same values as the scent and fan nodes use.
3. Upload again. You should see `[net] ... MQTT 10.42.0.1:1883 ... connected`.
4. On the Pi, check it arrives:
   `mosquitto_sub -h localhost -t 'xrpod/iaq/#' -v -u <user> -P <password>`

The Pi needs `SCENT_HARDWARE=mqtt` (already set for the scent node) for
`pi/scent.py` to pick the readings up.

## Code

- `src/main.cpp`: wiring to hardware and network.
- `src/IaqSensor.*`: the BME688, read without blocking; finds it at 0x77
  or 0x76.
- `lib/iaq_core`: hardware-free logic (reading JSON, scent detection from the
  gas value, reading the scent node's state), with unit tests:
  `pio test -e native` (needs a host C++ compiler).
