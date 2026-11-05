export const SCENTS = ["none", "lavender", "pine", "citrus", "ocean", "rain"];
// Mirror CONTROL_MODES and ENVIRONMENTS in pi/store.py.
export const CONTROL_MODES = ["manual", "auto"];
export const ENVIRONMENTS = ["none", "beach", "forest", "desert", "sponsor"];
// Mirrors STALE_SECONDS in pi/vr.py: no headset news for this long means "not connected".
export const VR_STALE_SECONDS = 15;

// Mirrors DEFAULT_SETTINGS in pi/store.py, which owns the real values.
export const DEFAULT_SETTINGS = {
  target_temp_f: 72,
  target_humidity_pct: 45,
  fan_speed_pct: 0,
  ac_on: false,
  heater_on: false,
  selected_scent: "none",
  scent_intensity_pct: 50,
  control_mode: "manual",
  selected_environment: "none",
};

export const SETTINGS_FIELDS = Object.keys(DEFAULT_SETTINGS);

export const FIELD_LABELS = {
  target_temp_f: "Target temp",
  target_humidity_pct: "Target humidity",
  fan_speed_pct: "Fan speed",
  ac_on: "AC",
  heater_on: "Heater",
  selected_scent: "Scent",
  scent_intensity_pct: "Scent intensity",
  control_mode: "Mode",
  selected_environment: "Environment",
};

// Human-readable rendering of a stringified settings value for the history list.
export function formatFieldValue(field, value) {
  if (value === null || value === undefined || value === "") return "—";
  switch (field) {
    case "ac_on":
    case "heater_on":
      return value === "true" ? "on" : value === "false" ? "off" : value;
    case "target_temp_f":
      return `${value}°F`;
    case "target_humidity_pct":
    case "fan_speed_pct":
    case "scent_intensity_pct":
      return `${value}%`;
    default:
      return value;
  }
}