# XRPod scent / IAQ ESP32 node

PlatformIO (Arduino framework) project for the ESP32 WROOM-32 Type-C DevKit that
drives the scent module and reports to the Raspberry Pi 5 over MQTT.

## Open it
Open `esp32/xrpod-esp32.code-workspace` in VS Code (File > Open Workspace from File).
PlatformIO picks up this folder; Git tracks the whole XRPod repo.

## Build / upload / monitor
Bottom status bar in VS Code:
- check mark = Build
- right arrow = Upload (if it sits on "Connecting...", hold the board's BOOT button)
- plug icon = Serial Monitor (115200 baud)

## Wi-Fi + MQTT
Copy `include/secrets.example.h` to `include/secrets.h` and fill it in.
`secrets.h` is git-ignored.

MQTT topics: `xrpod/scent/status` (publish), `xrpod/scent/cmd` (subscribe).
