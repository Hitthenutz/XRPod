import { useEffect, useState } from "react";
import { getVrFrame } from "@/api/pod";

// The headset sends about 8 pictures a second; ask a bit faster so the HUD
// shows each one soon after it arrives. One request at a time.
const POLL_MS = 80;
// After an error (e.g. the Pi is unreachable), wait before trying again.
const RETRY_MS = 2000;

/*
The headset's live view, while `enabled` and this tab is visible.
'src' is an object URL for an <img>, or null when the headset isn't sending
(it's off, in another app, or the live view is turned off in the app).
*/
export function useVrLiveView(enabled) {
  const [src, setSrc] = useState(null);

  useEffect(() => {
    if (!enabled) {
      setSrc(null);
      return undefined;
    }
    let stopped = false;
    let timer = null;
    let url = null;
    const controller = new AbortController();

    const show = (blob) => {
      const next = blob ? URL.createObjectURL(blob) : null;
      setSrc(next);
      if (url) URL.revokeObjectURL(url);
      url = next;
    };

    const tick = async () => {
      if (stopped) return;
      let wait = POLL_MS;
      if (document.visibilityState === "visible") {
        try {
          show(await getVrFrame(controller.signal));
        } catch (err) {
          if (stopped) return;
          console.error("failed to load the VR live view:", err);
          show(null);
          wait = RETRY_MS;
        }
      }
      if (!stopped) timer = setTimeout(tick, wait);
    };
    tick();

    return () => {
      stopped = true;
      clearTimeout(timer);
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [enabled]);

  return src;
}
