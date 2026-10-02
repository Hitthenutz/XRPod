// Mirrors the enum in base44/entities/PodSettings.jsonc, SCENTS in
// pi-agent/agent.py and SCENT_NAMES in esp32-scent/esp32-scent.ino.
export const SCENTS = ["none", "lavender", "pine", "citrus", "ocean", "rain"];

// Mirrors minimum/maximum of target_temp_f in PodSettings.jsonc.
export const TEMP_RANGE_F = { min: 50, max: 95 };

// Mirrors the defaults in base44/entities/PodSettings.jsonc.
export const DEFAULT_SETTINGS = {
  target_temp_f: 72,
  target_humidity_pct: 45,
  fan_speed_pct: 0,
  ac_on: false,
  heater_on: false,
  selected_scent: "none",
  scent_intensity_pct: 50,
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

export const stringifyValue = (value) =>
  value === null || value === undefined ? null : String(value);
