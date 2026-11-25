import { Wind } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Slider } from "@/components/ui/Slider";
import { FAN_LEVELS } from "@/lib/podSettings";

export function AirflowCard({ settings, reading, onChange }) {  
  return (
    <Card title="Humidity & airflow" icon={Wind}>
      <div className="space-y-5">
        <Slider
          label="Target humidity"
          value={settings.target_humidity_pct}
          unit="%"
          accent="teal"
          onCommit={(v) => onChange({ target_humidity_pct: v })}
        />
      <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/60 px-4 py-2.5">
          <span className="text-xs uppercase tracking-wider text-slate-400">Live humidity</span>
          <span className="font-mono text-sm tabular-nums text-slate-200">
            {typeof reading?.actual_humidity_pct === "number" ? `${Math.round(reading.actual_humidity_pct)}%` : "--"}
          </span>
        </div>

        <div>
          <div className="mb-2 flex items-baseline justify-between">
            <span className="text-sm text-slate-300">Fan level</span>
            <span className="font-mono text-2xl font-semibold tabular-nums text-slate-50">
              {settings.fan_speed_pct}
              <span className="ml-0.5 text-base text-slate-400">%</span>
            </span>
          </div>
          <div role="radiogroup" aria-label="Fan level" className="grid grid-cols-5 gap-2">
            {FAN_LEVELS.map((level) => {
              const selected = settings.fan_speed_pct === level;
              return (
                <button
                  key={level}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => onChange({ fan_speed_pct: level })}
                  className={`flex min-h-12 items-center justify-center rounded-xl border px-2 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 ${
                    selected
                      ? "border-sky-400/70 bg-sky-500/15 text-sky-200"
                      : "border-slate-700 bg-slate-800/60 text-slate-300 hover:bg-slate-800"
                  }`}
                >
                  {level === 0 ? "Off" : level}
                </button>
              );
            })}
          </div>
          <div className="mt-3 flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/60 px-4 py-2.5">
            <span className="text-xs uppercase tracking-wider text-slate-400">Live fan speed</span>
            <span className="font-mono text-sm tabular-nums text-slate-200">
              {typeof reading?.fan_rpm === "number" ? `${Math.round(reading.fan_rpm)} rpm` : "--"}
            </span>
          </div>
        </div>
      </div>
    </Card>
  );
}