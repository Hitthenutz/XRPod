import {
  BrainCircuit,
  ShieldCheck,
  Wifi,
  WifiOff,
} from "lucide-react";

export function AIStatusCard({ settings, aiStatus, connected }) {
  // Determine whether automatic control is enabled
  const isAuto = settings?.control_mode === "auto";

  // Check whether the AI is actively recommending settings
  const active = isAuto && aiStatus?.active === true;

  // Physical environment prediction from the trained ML model
  const physicalEnvironment =
    aiStatus?.physical_environment ?? "UNKNOWN";

  // Confidence score from the trained Random Forest
  const confidence = aiStatus?.model_confidence;

  const confidenceDisplay =
    typeof confidence === "number" && Number.isFinite(confidence)
      ? `${(confidence * 100).toFixed(1)}%`
      : "—";

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5">

      {/* HEADER */}
      <div className="mb-5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BrainCircuit className="h-6 w-6 text-sky-400" />

          <div>
            <h2 className="text-lg font-semibold">
              XRPOD AI Supervisor
            </h2>

            <p className="text-xs text-slate-400">
              Environment-aware AI monitoring
            </p>
          </div>
        </div>

        {connected ? (
          <Wifi className="h-5 w-5 text-emerald-400" />
        ) : (
          <WifiOff className="h-5 w-5 text-amber-400" />
        )}
      </div>

      {/* CONTROL MODE */}
      <div className="mb-5 flex flex-wrap gap-2">
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ${
            isAuto
              ? "bg-sky-500/20 text-sky-300"
              : "bg-slate-700 text-slate-300"
          }`}
        >
          {isAuto ? "AUTO MODE" : "MANUAL MODE"}
        </span>

        <span className="rounded-full bg-slate-800 px-3 py-1 text-xs">
          {active ? "RECOMMENDING" : "STANDBY"}
        </span>
      </div>

      {!connected || !aiStatus ? (
        <p className="text-sm text-slate-400">
          Waiting for live AI updates from Raspberry Pi...
        </p>
      ) : (
        <>
          {/* VR ENVIRONMENT INFORMATION */}
          <div className="grid grid-cols-2 gap-3">

            <div className="rounded-xl bg-slate-800 p-3">
              <p className="text-xs text-slate-400">
                VR Environment
              </p>
              <p className="mt-1 font-semibold capitalize">
                {aiStatus.environment ?? "Unknown"}
              </p>
            </div>

            <div className="rounded-xl bg-slate-800 p-3">
              <p className="text-xs text-slate-400">
                Current Zone
              </p>
              <p className="mt-1 font-semibold capitalize">
                {aiStatus.zone ?? "Unknown"}
              </p>
            </div>

            <div className="rounded-xl bg-slate-800 p-3">
              <p className="text-xs text-slate-400">
                Recommended Temperature
              </p>
              <p className="mt-1 text-xl font-semibold">
                {active
                  ? `${aiStatus.target_temp_f}°F`
                  : "—"}
              </p>
            </div>

            <div className="rounded-xl bg-slate-800 p-3">
              <p className="text-xs text-slate-400">
                Recommended Fan Speed
              </p>
              <p className="mt-1 text-xl font-semibold">
                {active
                  ? `${aiStatus.fan_speed_pct}%`
                  : "—"}
              </p>
            </div>
          </div>

          {/* TRAINED MACHINE LEARNING MODEL */}
          <div className="mt-5 rounded-xl border border-sky-500/20 bg-sky-500/10 p-4">

            <div className="mb-4 flex items-center gap-2">
              <BrainCircuit className="h-5 w-5 text-sky-400" />

              <h3 className="font-semibold text-sky-200">
                Physical Environment AI
              </h3>
            </div>

            <div className="grid grid-cols-2 gap-3">

              <div>
                <p className="text-xs text-slate-400">
                  ML Prediction
                </p>

                <p className="mt-1 text-lg font-semibold">
                  {physicalEnvironment}
                </p>
              </div>

              <div>
                <p className="text-xs text-slate-400">
                  Model Confidence
                </p>

                <p className="mt-1 text-lg font-semibold">
                  {confidenceDisplay}
                </p>
              </div>
            </div>

            {/* CONFIDENCE BAR */}
            <div className="mt-4">
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-700">
                <div
                  className="h-full rounded-full bg-sky-400 transition-all duration-500"
                  style={{
                    width: `${
                      typeof confidence === "number" &&
                      Number.isFinite(confidence)
                        ? Math.max(0, Math.min(100, confidence * 100))
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>

            <p className="mt-3 text-xs text-slate-400">
              Experimental Random Forest model trained on
              simulated environmental data. Monitoring only.
            </p>
          </div>

          {/* AI REASONING */}
          <div className="mt-4 rounded-xl bg-slate-800/50 p-3">
            <p className="mb-1 text-xs font-semibold text-slate-300">
              AI Recommendation Reason
            </p>

            <p className="text-sm text-slate-400">
              {aiStatus.reason ?? "No recommendation available"}
            </p>
          </div>
        </>
      )}

      {/* SAFETY STATUS */}
      <div className="mt-5 flex items-center gap-2 border-t border-slate-800 pt-4 text-xs text-emerald-400">
        <ShieldCheck className="h-4 w-4" />
        Recommendation-only simulation — AI hardware control disabled
      </div>
    </section>
  );
}
