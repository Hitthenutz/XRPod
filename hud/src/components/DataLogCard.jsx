import { useState } from "react";
import {
  AlertOctagon,
  AlertTriangle,
  Circle,
  Database,
  Download,
  Info,
  Square,
  Trash2,
} from "lucide-react";
import { logCsvUrl } from "@/api/pod";
import { Card } from "@/components/ui/Card";
import { useChangeLog } from "@/hooks/useChangeLog";
import { useDataLog } from "@/hooks/useDataLog";
import { FIELD_LABELS, formatFieldValue } from "@/lib/podSettings";
import { timeAgo, useNow } from "@/lib/time";

// A settings change (the old History card) as a log line.
const settingsEvent = (c) => ({
  id: `s${c.id}`,
  created_date: c.created_date,
  level: "info",
  source: c.changed_by ? `settings · ${c.changed_by}` : "settings",
  message: `${FIELD_LABELS[c.field_name] ?? c.field_name}: ${formatFieldValue(c.field_name, c.old_value)} → ${formatFieldValue(c.field_name, c.new_value)}`,
});

const LEVEL_STYLE = {
  info: { icon: Info, tone: "text-slate-400" },
  warning: { icon: AlertTriangle, tone: "text-amber-300" },
  error: { icon: AlertOctagon, tone: "text-red-300" },
};

function duration(seconds) {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const pad = (n) => String(n).padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`;
}

function DownloadLink({ href, children }) {
  return (
    <a
      href={href}
      download
      className="inline-flex items-center gap-1 rounded-lg border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800"
    >
      <Download className="h-3.5 w-3.5" aria-hidden />
      {children}
    </a>
  );
}

function Recorder({ recording, onStart, onStop, now }) {
  const [name, setName] = useState("");
  if (recording) {
    const elapsed = (now - new Date(recording.started_date).getTime()) / 1000;
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3">
        <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-500" />
        <span className="min-w-0 flex-1 text-sm text-red-100">
          Recording <span className="font-semibold">{recording.name}</span>
          <span className="ml-2 font-mono tabular-nums text-red-200">{duration(elapsed)}</span>
        </span>
        <button
          type="button"
          onClick={onStop}
          className="flex items-center gap-1.5 rounded-lg bg-red-500/80 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-500"
        >
          <Square className="h-3.5 w-3.5" aria-hidden /> Stop
        </button>
      </div>
    );
  }
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={async (e) => {
        e.preventDefault();
        if (await onStart(name)) setName("");
      }}
    >
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        maxLength={64}
        placeholder="Session name (optional), e.g. Participant 3"
        aria-label="Session name"
        className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:border-sky-500 focus:outline-none"
      />
      <button
        type="submit"
        className="flex items-center gap-1.5 rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm font-medium text-red-200 hover:bg-red-500/20"
      >
        <Circle className="h-3.5 w-3.5 fill-red-500 text-red-500" aria-hidden /> Start recording
      </button>
    </form>
  );
}

function EventList({ events, now, empty }) {
  if (events.length === 0) return <p className="py-6 text-center text-sm text-slate-500">{empty}</p>;
  return (
    <ol className="max-h-72 divide-y divide-slate-800 overflow-y-auto pr-1">
      {events.map((e) => {
        const style = LEVEL_STYLE[e.level] ?? LEVEL_STYLE.info;
        const Icon = style.icon;
        return (
          <li key={e.id} className="flex items-start gap-3 py-2 text-sm">
            <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${style.tone}`} aria-label={e.level} />
            <div className="min-w-0 flex-1">
              <div className="text-slate-200">{e.message}</div>
              <div className="text-xs tracking-wider text-slate-500">{e.source}</div>
            </div>
            <time
              dateTime={e.created_date}
              title={new Date(e.created_date).toLocaleString()}
              className="shrink-0 text-xs text-slate-500"
            >
              {timeAgo(e.created_date, now)}
            </time>
          </li>
        );
      })}
    </ol>
  );
}

/**
 * The data log: record sessions, see what happens (and what goes wrong)
 * live, and download it all as CSV for Excel / MATLAB.
 */
export function DataLogCard() {
  const { events, sessions, recording, loading, error, start, stop, remove } = useDataLog();
  const { entries: changes } = useChangeLog(50);
  const [tab, setTab] = useState("activity");
  const now = useNow(1000);
  const problems = events.filter((e) => e.level !== "info");
  // Activity: pod events and settings changes together, newest first.
  const activity = [...events, ...changes.map(settingsEvent)].sort((a, b) =>
    b.created_date.localeCompare(a.created_date),
  );
  const shown = tab === "problems" ? problems : activity;
  const past = sessions.filter((s) => !s.recording).slice(0, 5);

  const tabClass = (name) =>
    `rounded-lg px-3 py-1.5 text-xs font-medium ${
      tab === name ? "bg-slate-700 text-slate-100" : "text-slate-400 hover:bg-slate-800"
    }`;

  return (
    <Card title="Data log" icon={Database} className="md:col-span-2">
      <div className="space-y-4">
        <Recorder recording={recording} onStart={start} onStop={stop} now={now} />
        {error && <p className="text-sm text-red-300">{error.message}</p>}

        <div>
          <div className="mb-2 flex items-center gap-1" role="tablist">
            <button type="button" role="tab" aria-selected={tab === "activity"} className={tabClass("activity")}
              onClick={() => setTab("activity")}>
              Activity
            </button>
            <button type="button" role="tab" aria-selected={tab === "problems"} className={tabClass("problems")}
              onClick={() => setTab("problems")}>
              Warnings &amp; errors
              {problems.length > 0 && (
                <span className="ml-1.5 rounded-full bg-amber-500/20 px-1.5 text-amber-300">{problems.length}</span>
              )}
            </button>
          </div>
          {loading ? (
            <p className="py-6 text-center text-sm text-slate-500">Loading…</p>
          ) : (
            <EventList
              events={shown}
              now={now}
              empty={tab === "problems" ? "No warnings or errors." : "Nothing logged yet."}
            />
          )}
        </div>

        <div className="space-y-2 border-t border-slate-800 pt-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
            <span className="mr-1">Last hour:</span>
            <DownloadLink href={logCsvUrl("readings", { minutes: 60 })}>Readings CSV</DownloadLink>
            <DownloadLink href={logCsvUrl("events", { minutes: 60 })}>Events CSV</DownloadLink>
          </div>
          {past.length > 0 && (
            <ul className="divide-y divide-slate-800">
              {past.map((s) => (
                <li key={s.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-slate-200">{s.name}</div>
                    <div className="text-xs text-slate-500">
                      {timeAgo(s.started_date, now)} · {duration(s.duration_s)} · {s.readings} readings
                    </div>
                  </div>
                  <DownloadLink href={logCsvUrl("readings", { session: s.id })}>Readings</DownloadLink>
                  <DownloadLink href={logCsvUrl("events", { session: s.id })}>Events</DownloadLink>
                  <button
                    type="button"
                    aria-label={`Delete ${s.name}`}
                    title="Delete this session (its readings then expire after 24 h)"
                    onClick={() => window.confirm(`Delete session "${s.name}"?`) && remove(s.id)}
                    className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-800 hover:text-red-300"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Card>
  );
}
