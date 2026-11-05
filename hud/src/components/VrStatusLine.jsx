import { Headset } from "lucide-react";
import { useVrState } from "@/hooks/useVrState";
import { timeAgo } from "@/lib/time";

// "beach-waterline (cool)", "no zone", or "zones not tracked". The zone id is
// what auto mode's recipes use (vr/docs/ZONES.md); the type is only a hint.
function zoneText(vr) {
  if (!vr.zone_tracking) return "zones not tracked";
  if (!vr.zone_id) return "no zone";
  return vr.zone_type === "neutral" ? vr.zone_id : `${vr.zone_id} (${vr.zone_type})`;
}

// "none": no world picked; the headset shows its waiting room.
const waiting = (env) => env === "none";

/** One line showing what the headset last reported, e.g. "VR: beach / beach-waterline (cool)". */
export function VrStatusLine({ selectedEnvironment }) {
  const { vr, connected } = useVrState();
  // The researcher picked a world (or "none", the headset's waiting room)
  // but the headset still shows another one.
  const mismatch = connected && vr.environment !== selectedEnvironment;

  return (
    <div
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-slate-800 bg-slate-950/60 px-4 py-3 text-sm"
      aria-live="polite"
    >
      <span className={`h-2.5 w-2.5 rounded-full ${connected ? "bg-emerald-400" : "bg-slate-600"}`} />
      <Headset className="h-4 w-4 text-slate-400" aria-hidden />
      {connected ? (
        <span className="text-slate-100">
          {waiting(vr.environment) ? (
            "VR: waiting room (no world picked)"
          ) : (
            <>
              VR: <span className="capitalize">{vr.environment}</span> / {zoneText(vr)}
            </>
          )}
        </span>
      ) : (
        <span className="text-slate-400">
          VR: not connected
          {vr && <span className="text-slate-500"> · last heard {timeAgo(vr.received_date)}</span>}
        </span>
      )}
      {mismatch && (
        <span className="text-amber-300">
          {waiting(selectedEnvironment)
            ? "Headset hasn’t gone back to the waiting room yet"
            : `Headset hasn’t switched to ${selectedEnvironment} yet`}
        </span>
      )}
    </div>
  );
}