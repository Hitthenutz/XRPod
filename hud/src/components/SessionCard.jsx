import { Bot, Hand, SlidersHorizontal } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { CONTROL_MODES, ENVIRONMENTS } from "@/lib/podSettings";
import { VrStatusLine } from "@/components/VrStatusLine";
// Label, icon and hint for each mode in CONTROL_MODES.
const MODE_UI = {
  manual: { label: "Manual", icon: Hand, hint: "You control the hardware with the cards below." },
  auto: {
    label: "Auto",
    icon: Bot,
    hint: "The pod’s control logic sets the hardware. Switch to Manual to take over.",
  },
};

export function SessionCard({ settings, onChange }) {
  return (
    <Card title="Session" icon={SlidersHorizontal} className="md:col-span-2">
      <div className="space-y-5">
        {/* Step 4: Manual / Auto switch */}
        <div>
          <div role="radiogroup" aria-label="Control mode" className="grid grid-cols-2 gap-2">
            {CONTROL_MODES.map((mode) => {
              const { label, icon: Icon } = MODE_UI[mode];
              const selected = settings.control_mode === mode;
              return (
                <button
                  key={mode}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => onChange({ control_mode: mode })}
                  className={`flex min-h-14 items-center justify-center gap-2 rounded-xl border px-4 py-3 font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 ${
                    selected
                      ? "border-sky-500/60 bg-sky-500/15 text-sky-300"
                      : "border-slate-700 bg-slate-800/60 text-slate-300 hover:bg-slate-800"
                  }`}
                >
                  <Icon className="h-5 w-5" aria-hidden />
                  {label}
                </button>
              );
            })}
          </div>
          <p className="mt-2 text-xs text-slate-400">{MODE_UI[settings.control_mode]?.hint}</p>
        </div>

        {/* Step 5: environment picker */}
        <div>
          <p className="mb-2 text-sm text-slate-300">Environment</p>
          <div
            role="radiogroup"
            aria-label="Environment"
            className="grid grid-cols-3 gap-2 sm:grid-cols-5"
          >
            {ENVIRONMENTS.map((env) => {
              const selected = settings.selected_environment === env;
              return (
                <button
                  key={env}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => onChange({ selected_environment: env })}
                  className={`min-h-12 rounded-xl border px-2 py-2 text-sm font-medium capitalize transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 ${
                    selected
                      ? "border-emerald-400/70 bg-emerald-500/15 text-emerald-200"
                      : "border-slate-700 bg-slate-800/60 text-slate-300 hover:bg-slate-800"
                  }`}
                >
                  {env}
                </button>
              );
          })}
        </div>
      </div>

      <VrStatusLine selectedEnvironment={settings.selected_environment} />
    </div>
  </Card>
);
}