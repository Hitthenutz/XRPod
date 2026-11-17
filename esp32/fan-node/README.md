# Fan node (ESP32-S3)

ESP32-S3 sketch that drives the Corsair RS120 fans (4-pin PWM) and reads their speed.

- Board: "ESP32S3 Dev Module" in Arduino IDE (esp32 core 3.x).
- Wiring: fan pin 4 (PWM) to GPIO 4, fan pin 3 (tach) to GPIO 5, fan pin 1 (GND)
  to the 12 V supply's minus AND an ESP32 GND, fan pin 2 to 12 V plus.
  12 V never touches the ESP32.
- Open `fan-node.ino` in Arduino IDE. Put the Wi-Fi name and password in it before uploading. Don't commit them.
- API: `GET /fan?pct=0-100` sets the speed, `GET /status` reads it. Both return
  `{"fan_pct": 80, "fan_rpm": 1680}`. The board also answers as `xrpod-fan.local`.
- Fail-safe: if nothing talks to it for 30 s, it turns the fans off. The Pi
  checks in every 2 s, so this only happens when the Pi is gone.
- The Pi uses it when `FAN_ESP32_URL` is set (see `pi/xrpod.service`).
- This node uses plain HTTP rather than MQTT because the Pi has no MQTT client
  yet and `pi/` stays standard-library Python. It can move to
  `xrpod/fan/cmd` / `xrpod/fan/state` once the Pi has an MQTT bridge.
