import { useEffect, useState} from 'react';
import { getVrState, subscribe } from "@/api/pod";
import { VR_STALE_SECONDS } from "@/lib/podSettings";
import { useNow } from "@/lib/time";

/*
The Pi only sends a live  "vr" event  when the headset's state changes, also ask every few seconds. 
That keeps "connected" right while the user 
stands still, and notices when the pi itself is out of reach.
*/
const POLL_MS = 5000;

//A slow reply can arrive after a newer live event. don't let it win
const isOlder = (a, b) => a && b && a.session_id === b.session_id && a.seq < b.seq;
/* 
What the headset last reported, via the Pi.
'vr' is null until the first message; 'connected' turns false after VR_STALE_SECONDS without news. 
 */ 
export function useVrState() {
//'at' is when this device reported 'state', for counting its age.  
  const [snap, setSnap] = useState(null);
  const now = useNow(1000);

  useEffect(() => {
    let canceled = false;
    const keep = (state) => {
        if (canceled) return;
        setSnap((prev) => (isOlder(state, prev?.state) ? prev : { state, at: Date.now() }));
    };
    const load = () => 
        getVrState()
    .then(keep)
    .catch((err) => console.error(" failed to load VR state:", err));

    load();
    const timer = setInterval(load, POLL_MS);
    const unsubscribe = subscribe({ vr: keep, open: load});

    return () => {
      canceled = true;
      clearInterval(timer);
      unsubscribe();
    }

}, []);

const vr = snap?.state ?? null;
  const ageS = vr ? vr.age_s + (now - snap.at) / 1000 : Infinity;
  return { vr, connected: Boolean(vr?.connected) && ageS <= VR_STALE_SECONDS };
}