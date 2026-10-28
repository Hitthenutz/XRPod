# Thermal (heater and AC)

Owner: TBD

Placeholder. Put this subsystem's ESP32 firmware in `firmware/` and its
design notes in `docs/DESIGN.md`; see [`../README.md`](../README.md) and
copy the layout of [`../iaq/`](../iaq/README.md).

Where it's wired up today:

- Pi: `set_heater_relay()` and `set_ac_relay()` in `pi/hardware.py`, stubs
  written for Pi GPIO relays. Once this subsystem has its own ESP32, they
  should send MQTT commands instead.
- Settings: `target_temp_f`, `target_humidity_pct`, `heater_on`, `ac_on`.
- HUD: `hud/src/components/TemperatureCard.jsx`.
- Temperature and humidity readings currently come from the IAQ node.

The heater and AC must never run together. That is enforced in the HUD, in
`validate_patch()` (`pi/store.py`) and in `apply_settings()`
(`pi/hardware.py`), and the firmware should enforce it too.
