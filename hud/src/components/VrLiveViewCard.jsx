import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { useVrLiveView } from "@/hooks/useVrLiveView";

/** What the person in the headset sees, a few pictures a second. */
export function VrLiveViewCard() {
  // Off saves the Wi-Fi when nobody is watching; the headset keeps sending.
  const [watching, setWatching] = useState(true);
  const src = useVrLiveView(watching);

  return (
    <Card
      title="Headset view"
      icon={Eye}
      className="md:col-span-2"
      action={
        <button
          type="button"
          onClick={() => setWatching((w) => !w)}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
        >
          {watching ? <EyeOff className="h-3.5 w-3.5" aria-hidden /> : <Eye className="h-3.5 w-3.5" aria-hidden />}
          {watching ? "Hide" : "Show"}
        </button>
      }
    >
      <div className="relative aspect-video overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
        {src ? (
          <>
            <img src={src} alt="What the headset user sees right now" className="h-full w-full object-cover" />
            <span className="absolute left-3 top-3 flex items-center gap-1.5 rounded-md bg-black/60 px-2 py-1 text-xs font-semibold text-red-300">
              <span className="h-2 w-2 rounded-full bg-red-500" /> LIVE
            </span>
          </>
        ) : (
          <div className="flex h-full items-center justify-center px-6 text-center text-sm text-slate-500">
            {watching
              ? "No picture from the headset. Is the XRPod app open on it and connected?"
              : "Live view hidden."}
          </div>
        )}
      </div>
    </Card>
  );
}
