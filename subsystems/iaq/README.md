# Scent / IAQ node

An ESP32 with two BME688 sensors (air quality + scent detection) and two
atomizers, talking MQTT to the scent hub in `pi/scent.py` on the
Raspberry Pi. How it works, the MQTT topics and what's still missing:
[docs/DESIGN.md](docs/DESIGN.md).

```
subsystems/iaq/
├── docs/DESIGN.md               # architecture, MQTT contract, MISSING list
└── firmware/scent-node/         # PlatformIO project (ESP32)
    ├── include/config.h         # pins, atomizer type, limits
    ├── include/secrets.example.h
    ├── src/main.cpp             # Wi-Fi, MQTT, commands
    ├── src/atomizer.cpp         # the only code that touches the atomizers
    ├── src/sensors.cpp          # the two BME688s (BSEC2)
    └── test/host/               # atomizer test that runs on a PC
pi/scent.py                      # the hub (runs inside pi/agent.py)
pi/tools/record.py               # record sensor data to CSV
pi/mosquitto.conf                # broker settings for the Pi
```

## Build and flash the node

Needs [PlatformIO](https://platformio.org/install/cli) (`pip install platformio`).

```bash
cd subsystems/iaq/firmware/scent-node
cp include/secrets.example.h include/secrets.h   # then fill in Wi-Fi + MQTT login
pio run                     # must finish with 0 warnings
pio run -t upload           # flash over USB
pio device monitor          # logs; lines start with "#"
```

Set the hardware in `include/config.h` first: `ATOMIZER_TYPE`
(`MIST_MODULE` or `AN6_MOTOR`), the pins, and the BME688 addresses.
Until the pins are set, the node runs the sensors but refuses every
atomizer command.

## Host atomizer test

Tests `src/atomizer.cpp` on your PC against a fake Arduino API. It builds
for both atomizer types and for an unwired board:

```bash
cd subsystems/iaq/firmware/scent-node
sh test/host/run.sh                         # needs g++ or clang++
CXX="python -m ziglang c++" sh test/host/run.sh   # or: pip install ziglang
```

Each line should end in `OK`.

## Set up the Pi

1. **Install the broker and the MQTT library:**
   ```bash
   sudo apt install mosquitto python3-paho-mqtt
   sudo cp ~/XRPod/pi/mosquitto.conf /etc/mosquitto/conf.d/xrpod.conf
   ```
2. **Create the logins** (one for the node, one for the agent):
   ```bash
   sudo mosquitto_passwd -c /etc/mosquitto/xrpod.passwd scent1   # same as MQTT_USER/PASS in secrets.h
   sudo mosquitto_passwd /etc/mosquitto/xrpod.passwd xrpod
   sudo chown root:mosquitto /etc/mosquitto/xrpod.passwd
   sudo chmod 640 /etc/mosquitto/xrpod.passwd
   sudo systemctl enable --now mosquitto
   sudo systemctl restart mosquitto
   ```
3. **Give the agent its login.** `pi/xrpod.service` already sets
   `MQTT_HOST=127.0.0.1` and reads the rest from `/etc/xrpod.env`:
   ```bash
   printf 'MQTT_USER=xrpod\nMQTT_PASS=the-password-from-step-2\n' | sudo tee /etc/xrpod.env
   sudo chmod 600 /etc/xrpod.env
   ```
4. **Start on boot.** Install `pi/xrpod.service` as in the main
   [README](../../README.md#run-it-on-the-pi). It starts after Mosquitto and
   restarts on failure, and the hub runs inside it, so there's no separate
   service. Then:
   ```bash
   sudo systemctl restart xrpod
   journalctl -u xrpod -f      # look for "scent: MQTT broker 127.0.0.1:1883"
   ```

Check that the node is talking:

```bash
mosquitto_sub -u xrpod -P 'the-password' -t 'xrpod/scent/#' -v
```

## Record training and calibration data

`pi/tools/record.py` writes one CSV row per heater scan: time, node, label,
atomizer, duty, T/RH/P, `gas_ohm_0..9`, `prob_0..3`. It uses the same
`MQTT_*` variables as the agent:

```bash
export MQTT_USER=xrpod MQTT_PASS='the-password'
python3 pi/tools/record.py --label clean_air --minutes 30 --out data/clean_air.csv
python3 pi/tools/record.py --label lavender --out data/lavender.csv    # Ctrl+C to stop
```

- **AI-Studio training:** record clean air and each scent. Check that
  AI-Studio imports the CSV (MISSING #13 in DESIGN.md).
- **Calibration:** with clean air recorded, run each scent at 25/50/75/100 %
  from the HUD, recording each with its own `--label`. The response per
  duty sets `INTENSITY_PER_DUTY`, the spread sets `STRENGTH_TOL`, and the
  time until the response levels off sets `SETTLE_S` (top of `pi/scent.py`).

## Bench test without the HUD

```bash
MQTT_HOST=127.0.0.1 MQTT_USER=xrpod MQTT_PASS='…' python3 pi/scent.py lavender 60 30
```

That runs lavender at 60 % for 30 s and logs the check and the IAQ reading
every 2 s. Stop the agent first (`sudo systemctl stop xrpod`), so only one
hub sends commands.
