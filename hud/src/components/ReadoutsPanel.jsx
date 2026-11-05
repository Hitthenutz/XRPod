import { Droplets, Fan, Flame, Snowflake, Thermometer } from "lucide-react";
import { timeAgo, useNow } from "@/lib/time";

// If the Pi hasn't reported in this long, flag the readings as stale.
const STALE_AFTER_MS = 60_000;

function Stat({ icon: Icon, label, value, unit, sub, tone = "text-slate-50" }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
      <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-400">
        <Icon className="h-4 w-4" aria-hidden />
        {label}
      </div>
      <div className={`mt-2 font-mono text-4xl font-semibold tabular-nums sm:text-5xl ${tone}`}>
        {value}
        {unit && <span className="ml-1 text-xl text-slate-400">{unit}</span>}
      </div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

function RunningPill({ icon: Icon, label, running, color }) {
  return (
    <div
      className={`flex items-center justify-between rounded-xl border px-4 py-3 ${
        running
          ? color === "orange"
            ? "border-orange-500/50 bg-orange-500/10 text-orange-300"
            : "border-sky-500/50 bg-sky-500/10 text-sky-300"
          : "border-slate-800 bg-slate-950/60 text-slate-400"
      }`}
    >
      <span className="flex items-center gap-2 text-sm font-medium">
        <Icon className={`h-5 w-5 ${running ? "animate-pulse" : ""}`} aria-hidden />
        {label}
      </span>
      <span className="text-xs font-semibold uppercase tracking-wider">
        {running ? "Running" : "Idle"}
      </span>
    </div>
  );
}

const fmt = (n, digits = 1) =>
  typeof n === "number" && Number.isFinite(n) ? n.toFixed(digits) : "--";

export function ReadoutsPanel({ reading, loading }) {
  const now = useNow(5000);
  const lastAt = reading?.created_date ? new Date(reading.created_date).getTime() : null;
  const stale = !lastAt || now - lastAt > STALE_AFTER_MS;

  return (
    <section aria-label="Live readouts" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Live readouts
        </h2>
        <span className="flex items-center gap-2 text-xs text-slate-400">
          <span
            className={`h-2 w-2 rounded-full ${
              stale ? "bg-amber-500" : "bg-emerald-400 shadow-[0_0_8px] shadow-emerald-400"
            }`}
          />
          {loading
            ? "Connecting…"
            : lastAt
              ? `${stale ? "Stale · " : ""}updated ${timeAgo(lastAt, now)}`
              : "No readings yet"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Stat
          icon={Thermometer}
          label="Temperature"
          value={fmt(reading?.actual_temp_f)}
          unit="°F"
        />
        <Stat
          icon={Droplets}
          label="Humidity"
          value={fmt(reading?.actual_humidity_pct, 0)}
          unit="%"
        />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <RunningPill icon={Flame} label="Heater" running={!!reading?.heater_running} color="orange" />
        <RunningPill icon={Snowflake} label="AC" running={!!reading?.ac_running} color="sky" />
        <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/60 px-4 py-3 text-slate-400">
          <span className="flex items-center gap-2 text-sm font-medium">
            <Fan className="h-5 w-5" aria-hidden />
            Fan
          </span>
          <span className="font-mono text-sm tabular-nums text-slate-200">
            {typeof reading?.fan_rpm === "number" ? `${Math.round(reading.fan_rpm)} rpm` : "--"}
          </span>
        </div>
      </div>
    </section>
  );
}
