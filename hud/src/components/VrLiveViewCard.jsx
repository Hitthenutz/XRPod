import { useState } from "react";
import { ChevronDown, ChevronUp, Eye } from "lucide-react";
import { useVrLiveView } from "@/hooks/useVrLiveView";

// Remembered on this device so the card stays the way you left it.
const STORAGE_KEY = "xrpod.liveViewOpen";

function loadOpen() {
  try {
    return localStorage.getItem(STORAGE_KEY) !== "false";
  } catch {
    return true;
  }
}

function saveOpen(open) {
  try {
    localStorage.setItem(STORAGE_KEY, String(open));
  } catch {
    // Private browsing etc.: just not remembered.
  }
}

/**
 * What the person in the headset sees, several pictures a second. Hide
 * folds it into a slim bar and stops fetching pictures.
 */
export function VrLiveViewCard() {
  const [open, setOpen] = useState(loadOpen);
  const src = useVrLiveView(open);
  const toggle = () =>
    setOpen((o) => {
      saveOpen(!o);
      return !o;
    });

  return (
    <section
      className={`rounded-2xl border border-slate-800 bg-slate-900/70 shadow-lg shadow-black/20 md:col-span-2 ${
        open ? "p-5" : "px-5 py-3"
      }`}
    >
      <header className={`flex items-center justify-between gap-3 ${open ? "mb-4" : ""}`}>
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-slate-400">
          <Eye className="h-4 w-4" aria-hidden />
          Headset view
          {!open && <span className="text-xs font-normal normal-case tracking-normal text-slate-500">(hidden)</span>}
        </h2>
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
        >
          {open ? <ChevronUp className="h-3.5 w-3.5" aria-hidden /> : <ChevronDown className="h-3.5 w-3.5" aria-hidden />}
          {open ? "Hide" : "Show"}
        </button>
      </header>

      {open && (
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
              No picture from the headset. Is the XRPod app open on it and connected?
            </div>
          )}
        </div>
      )}
    </section>
  );
}
