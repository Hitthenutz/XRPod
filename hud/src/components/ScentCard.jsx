import { CircleCheck, CircleX, Loader2, Sparkles } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Slider } from "@/components/ui/Slider";
import { SCENTS } from "@/lib/podSettings";

const SCENT_SWATCH = {
  none: "bg-slate-500",
  lavender: "bg-violet-400",
  pine: "bg-emerald-500",
};

// The Pi's check that the right scent arrived at the right strength.
const CHECK_STYLE = {
  pass: { Icon: CircleCheck, label: "Verified", tone: "text-emerald-300" },
  fail: { Icon: CircleX, label: "Check failed", tone: "text-red-300" },
  pending: { Icon: Loader2, label: "Checking", tone: "text-slate-400", spin: true },
};

function ScentCheck({ check }) {
  if (!check) return null;
  const { Icon, label, tone, spin } = CHECK_STYLE[check.status] ?? CHECK_STYLE.pending;
  return (
    <p className={`flex items-start gap-2 text-sm ${tone}`} aria-live="polite">
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${spin ? "animate-spin" : ""}`} aria-hidden />
      <span>
        {label}
        {check.reason && <span className="text-slate-400"> · {check.reason}</span>}
      </span>
    </p>
  );
}

export function ScentCard({ settings, reading, onChange }) {
  const off = settings.selected_scent === "none";
  return (
    <Card title="Scent" icon={Sparkles}>
      <div className="space-y-5">
        <div role="radiogroup" aria-label="Scent" className="grid grid-cols-3 gap-2">
          {SCENTS.map((scent) => {
            const selected = settings.selected_scent === scent;
            return (
              <button
                key={scent}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => onChange({ selected_scent: scent })}
                className={`flex min-h-12 items-center justify-center gap-2 rounded-xl border px-2 py-2 text-sm font-medium capitalize transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 ${
                  selected
                    ? "border-violet-400/70 bg-violet-500/15 text-violet-200"
                    : "border-slate-700 bg-slate-800/60 text-slate-300 hover:bg-slate-800"
                }`}
              >
                <span className={`h-2.5 w-2.5 rounded-full ${SCENT_SWATCH[scent]}`} />
                {scent}
              </button>
            );
          })}
        </div>
        <Slider
          label="Intensity"
          value={settings.scent_intensity_pct}
          unit="%"
          accent="violet"
          disabled={off}
          onCommit={(v) => onChange({ scent_intensity_pct: v })}
        />
        {/* Readings lag a tick behind a change; don't show the old run's result. */}
        {!off &&
          reading?.scent_check?.scent === settings.selected_scent &&
          reading.scent_check.duty === settings.scent_intensity_pct && (
          <ScentCheck check={reading.scent_check} />
        )}
      </div>
    </Card>
  );
}
