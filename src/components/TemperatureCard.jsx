import { Flame, Snowflake, Thermometer } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Slider } from "@/components/ui/Slider";
import { Toggle } from "@/components/ui/Toggle";
import { TEMP_RANGE_F } from "@/lib/podSettings";

export function TemperatureCard({ settings, onChange }) {
  return (
    <Card title="Temperature" icon={Thermometer}>
      <div className="space-y-5">
        <Slider
          label="Target temperature"
          value={settings.target_temp_f}
          min={TEMP_RANGE_F.min}
          max={TEMP_RANGE_F.max}
          unit="°F"
          accent="orange"
          onCommit={(v) => onChange({ target_temp_f: v })}
        />
        {/* Heater and AC are mutually exclusive: turning one on turns the other off. */}
        <div className="flex flex-col gap-3 sm:flex-row">
          <Toggle
            label="Heater"
            icon={Flame}
            color="orange"
            checked={settings.heater_on}
            onChange={(on) => onChange(on ? { heater_on: true, ac_on: false } : { heater_on: false })}
          />
          <Toggle
            label="AC"
            icon={Snowflake}
            color="sky"
            checked={settings.ac_on}
            onChange={(on) => onChange(on ? { ac_on: true, heater_on: false } : { ac_on: false })}
          />
        </div>
      </div>
    </Card>
  );
}
