# Airflow (fan)

Owner: TBD

Placeholder. Put this subsystem's ESP32 firmware in `firmware/` and its
design notes in `docs/DESIGN.md`; see [`../README.md`](../README.md) and
copy the layout of [`../iaq/`](../iaq/README.md).

Where it's wired up today:

- Pi: `set_fan_pwm()` in `pi/hardware.py`, a stub written for Pi GPIO PWM.
  `fan_rpm` in `read_sensors()` is fake. Once this subsystem has its own
  ESP32, the Pi should send it MQTT commands instead.
- Settings: `fan_speed_pct` (0–100).
- HUD: `hud/src/components/AirflowCard.jsx`.
