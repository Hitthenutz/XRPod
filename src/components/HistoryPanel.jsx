import { useState } from "react";
import { ArrowRight, ChevronDown, History } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { useChangeLog } from "@/hooks/useChangeLog";
import { FIELD_LABELS, formatFieldValue } from "@/lib/podSettings";
import { timeAgo, useNow } from "@/lib/time";

export function HistoryPanel() {
  const [open, setOpen] = useState(true);
  const { entries, loading, error } = useChangeLog(50);
  const now = useNow(15000);

  return (
    <Card
      title="History"
      icon={History}
      action={
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-controls="history-list"
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-slate-800 hover:text-slate-200"
        >
          {open ? "Hide" : `Show (${entries.length})`}
          <ChevronDown className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} />
        </button>
      }
    >
      {open && (
        <div id="history-list">
          {loading ? (
            <p className="py-6 text-center text-sm text-slate-500">Loading…</p>
          ) : error && entries.length === 0 ? (
            <p role="alert" className="py-6 text-center text-sm text-red-300">
              Couldn’t load history. New changes will still show up here.
            </p>
          ) : entries.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-500">No changes yet.</p>
          ) : (
            <ol className="max-h-96 divide-y divide-slate-800 overflow-y-auto pr-1">
              {entries.map((e) => (
                <li key={e.id} className="flex items-center gap-3 py-2.5 text-sm">
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-slate-200">
                      {FIELD_LABELS[e.field_name] ?? e.field_name}
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5 font-mono text-xs text-slate-400">
                      <span>{formatFieldValue(e.field_name, e.old_value)}</span>
                      <ArrowRight className="h-3 w-3 text-slate-600" aria-label="to" />
                      <span className="text-slate-100">
                        {formatFieldValue(e.field_name, e.new_value)}
                      </span>
                      {e.changed_by && (
                        <span className="truncate text-slate-500">· {e.changed_by}</span>
                      )}
                    </div>
                  </div>
                  <time
                    dateTime={e.created_date}
                    title={e.created_date ? new Date(e.created_date).toLocaleString() : ""}
                    className="shrink-0 text-xs text-slate-500"
                  >
                    {timeAgo(e.created_date, now)}
                  </time>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </Card>
  );
}
