import { AlertTriangle, Loader2 } from "lucide-react";
import { AirflowCard } from "@/components/AirflowCard";
import { HistoryPanel } from "@/components/HistoryPanel";
import { ReadoutsPanel } from "@/components/ReadoutsPanel";
import { ScentCard } from "@/components/ScentCard";
import { TemperatureCard } from "@/components/TemperatureCard";
import { useLatestReading } from "@/hooks/useLatestReading";
import { usePodSettings } from "@/hooks/usePodSettings";

export default function App() {
  const { settings, applyChanges, error, saving } = usePodSettings();
  const { reading, loading: readingLoading } = useLatestReading();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-5xl px-4 pb-10 pt-[max(1.5rem,env(safe-area-inset-top))] sm:px-6">
        <header className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              XR<span className="text-sky-400">Pod</span>
            </h1>
            <p className="text-xs uppercase tracking-widest text-slate-500">Manual control HUD</p>
          </div>
          <span className="flex items-center gap-2 text-xs text-slate-400" aria-live="polite">
            {saving ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Saving…
              </>
            ) : settings ? (
              "Synced"
            ) : null}
          </span>
        </header>

        {error && (
          <div
            role="alert"
            className="mb-4 flex items-start gap-2 rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>Couldn’t reach the pod settings. {error.message ?? String(error)}</span>
          </div>
        )}

        <ReadoutsPanel reading={reading} loading={readingLoading} />

        {settings ? (
          <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
            <TemperatureCard settings={settings} onChange={applyChanges} />
            <AirflowCard settings={settings} onChange={applyChanges} />
            <ScentCard settings={settings} onChange={applyChanges} />
            <HistoryPanel />
          </div>
        ) : (
          !error && (
            <div className="flex justify-center py-16">
              <Loader2 className="h-6 w-6 animate-spin text-slate-500" />
            </div>
          )
        )}
      </div>
    </div>
  );
}
