import { Sparkles } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Slider } from "@/components/ui/Slider";
import { SCENTS } from "@/lib/podSettings";

const SCENT_SWATCH = {
  none: "bg-slate-500",
  lavender: "bg-violet-400",
  pine: "bg-emerald-500",
  citrus: "bg-amber-400",
  ocean: "bg-cyan-400",
  rain: "bg-indigo-400",
};

export function ScentCard({ settings, onChange }) {
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
      </div>
    </Card>
  );
}
