
import {
  BrainCircuit,
  ShieldCheck,
  Wifi,
  WifiOff,
} from "lucide-react";

export function AIStatusCard({ settings, aiStatus, connected }) {
  const isAuto = settings?.control_mode === "auto";
  const active = isAuto && aiStatus?.active === true;
  const confidence = aiStatus?.model_confidence;
  const effective = aiStatus?.effective_settings;

  const confidenceDisplay =
    typeof confidence === "number" && Number.isFinite(confidence)
      ? `${(confidence * 100).toFixed(1)}%`
      : "—";

  const confidenceWidth =
    typeof confidence === "number" && Number.isFinite(confidence)
      ? Math.max(0, Math.min(100, confidence * 100))
      : 0;

  const source = aiStatus?.control_source ?? "unknown";
  const authorized = aiStatus?.control_authorized === true;
  const executionMode = aiStatus?.execution_mode ?? "unknown";

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
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

      <div className="mb-5 flex flex-wrap gap-2">
        <span className="rounded-full bg-sky-500/20 px-3 py-1 text-xs font-semibold text-sky-300">
          {isAuto ? "AUTO MODE" : "MANUAL MODE"}
        </span>
        <span className="rounded-full bg-slate-800 px-3 py-1 text-xs">
          {active ? "RECOMMENDING" : "STANDBY"}
        </span>
        <span className="rounded-full bg-slate-800 px-3 py-1 text-xs uppercase">
          {executionMode}
        </span>
      </div>

      {!connected || !aiStatus ? (
        <p className="text-sm text-slate-400">
          Waiting for live AI updates from Raspberry Pi...
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3">
            <InfoTile
              label="VR Environment"
              value={aiStatus.environment ?? "Unknown"}
            />
            <InfoTile
              label="Current Zone"
              value={aiStatus.zone ?? "Unknown"}
            />
            <InfoTile
              label="Recommended Temperature"
              value={
                active && aiStatus.target_temp_f != null
                  ? `${aiStatus.target_temp_f}°F`
                  : "—"
              }
            />
            <InfoTile
              label="Recommended Fan Speed"
              value={
                active && aiStatus.fan_speed_pct != null
                  ? `${aiStatus.fan_speed_pct}%`
                  : "—"
              }
            />
          </div>

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
                  {aiStatus.physical_environment ?? "UNKNOWN"}
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

            <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-slate-700">
              <div
                className="h-full rounded-full bg-sky-400 transition-all duration-500"
                style={{ width: `${confidenceWidth}%` }}
              />
            </div>

            <p className="mt-3 text-xs text-slate-400">
              Experimental model trained on simulated data.
              Monitoring only.
            </p>
          </div>

          <div className="mt-5 rounded-xl border border-slate-700 bg-slate-800/50 p-4">
            <h3 className="mb-4 font-semibold">
              Control Arbiter
            </h3>

            <div className="grid grid-cols-2 gap-3">
              <InfoTile
                label="Control Source"
                value={source.toUpperCase()}
              />
              <InfoTile
                label="Decision Status"
                value={authorized ? "AUTHORIZED" : "FALLBACK"}
              />
              <InfoTile
                label="Preview Temperature"
                value={
                  effective?.target_temp_f != null
                    ? `${effective.target_temp_f}°F`
                    : "—"
                }
              />
              <InfoTile
                label="Preview Fan Speed"
                value={
                  effective?.fan_speed_pct != null
                    ? `${effective.fan_speed_pct}%`
                    : "—"
                }
              />
            </div>

            <div className="mt-4 border-t border-slate-700 pt-3">
              <p className="text-xs text-slate-400">
                Control Decision Reason
              </p>
              <p className="mt-1 text-sm">
                {aiStatus.control_reason ?? "Unavailable"}
              </p>
            </div>

            <p className="mt-3 text-xs text-slate-500">
              Decision generation: {aiStatus.control_generation ?? "—"}
            </p>
          </div>

          <div className="mt-4 rounded-xl bg-slate-800/50 p-3">
            <p className="mb-1 text-xs font-semibold">
              AI Recommendation Reason
            </p>
            <p className="text-sm text-slate-400">
              {aiStatus.reason ?? "No recommendation available"}
            </p>
          </div>
        </>
      )}

      <div className="mt-5 flex items-center gap-2 border-t border-slate-800 pt-4 text-xs text-emerald-400">
        <ShieldCheck className="h-4 w-4" />
        Preview only — AI commands are not applied to hardware
      </div>
    </section>
  );
}

function InfoTile({ label, value }) {
  return (
    <div className="rounded-xl bg-slate-800 p-3">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 font-semibold capitalize">{value}</p>
    </div>
  );
}
