import { useEffect, useState } from "react";
import { subscribe } from "@/api/pod";

export function useAIStatus() {
  const [aiStatus, setAIStatus] = useState(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const unsubscribe = subscribe({
      ai: (data) => {
        setAIStatus(data);
        setConnected(true);
      },

      open: () => {
        setConnected(false);
        setAIStatus(null);
      },
    });

    return unsubscribe;
  }, []);

  return {
    aiStatus,
    connected,
  };
}
