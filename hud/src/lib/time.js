import { useEffect, useState } from "react";

export function timeAgo(date, now = Date.now()) {
  if (!date) return "";
  const seconds = Math.max(0, Math.round((now - new Date(date).getTime()) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// Re-renders the caller every `intervalMs` so relative times stay fresh.
export function useNow(intervalMs = 10000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}
