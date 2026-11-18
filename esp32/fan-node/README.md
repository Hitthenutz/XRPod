# Fan node (ESP32-S3)

Arduino sketch that drives the Corsair RS120 fans (4-pin PWM, daisy-chained)
and reads their speed. It talks to the Pi over MQTT, the same way the scent
node does (topics in `docs/subsystems.md`; Pi side in `pi/fan.py`).

```
Pi (Mosquitto) --xrpod/fan/cmd {"fan_speed_pct":60}-------> ESP32 --> fan PWM
Pi <-----------xrpod/fan/state {"fan_speed_pct","fan_rpm","uptime_s"} (retained)
Pi <-----------xrpod/fan/node  "online" / "offline" (retained, last will)
Pi <-----------xrpod/fan/error {"error":"bad_json"}
```

- Board: "ESP32S3 Dev Module" in Arduino IDE (esp32 core 3.x).
- Libraries (Sketch > Include Library > Manage Libraries): **PubSubClient**
  by Nick O'Leary and **ArduinoJson** by Benoit Blanchon.
- Wiring: fan pin 4 (PWM) to GPIO 4, fan pin 3 (tach) to GPIO 5, fan pin 1
  (GND) to the 12 V supply's minus AND an ESP32 GND, fan pin 2 to 12 V plus.
  12 V never touches the ESP32.
- Put the Wi-Fi name and password (the Pi's hotspot) at the top of
  `fan-node.ino` before uploading, plus the broker login (`MQTT_USER` / `MQTT_PASSWORD`). Don't commit them. `MQTT_HOST` is the Pi,
  `10.42.0.1` on its hotspot.
- Fail-safe: no command from the Pi for 15 s turns the fans off. The Pi
  resends every 5 s, so this only happens when the Pi or the network is gone.
- The Pi uses it when `FAN_HARDWARE=mqtt` is set (see `pi/xrpod.service`).
  Bench test from the Pi: `FAN_HARDWARE=mqtt python3 pi/fan.py 60 20`.
