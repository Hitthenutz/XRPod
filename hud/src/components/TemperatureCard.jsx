import { Flame, Snowflake, Thermometer } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Slider } from "@/components/ui/Slider";
import { Toggle } from "@/components/ui/Toggle";

export function TemperatureCard({ settings, reading, onChange }) {
    return (
    <Card title="Temperature" icon={Thermometer}>
      <div className="space-y-5">
        <Slider
          label="Target temperature"
          value={settings.target_temp_f}
          min={50}
          max={95}
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
        <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/60 px-4 py-2.5">
          <span className="text-xs uppercase tracking-wider text-slate-400">Live temperature</span>
          <span className="font-mono text-sm tabular-nums text-slate-200">
            {typeof reading?.actual_temp_f === "number" ? `${reading.actual_temp_f.toFixed(1)}°F` : "--"}
          </span>
        </div>
      </div>
    </Card>
  );
}
