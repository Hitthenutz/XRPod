const ON_STYLES = {
  orange: "border-orange-500/60 bg-orange-500/15 text-orange-300",
  sky: "border-sky-500/60 bg-sky-500/15 text-sky-300",
};
const DOT_STYLES = {
  orange: "bg-orange-400 shadow-[0_0_10px] shadow-orange-400",
  sky: "bg-sky-400 shadow-[0_0_10px] shadow-sky-400",
};

/** Large, touch-friendly on/off button. */
export function Toggle({ label, icon: Icon, checked, onChange, color = "sky" }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`flex min-h-14 flex-1 items-center justify-between gap-3 rounded-xl border px-4 py-3 text-left font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 ${
        checked
          ? ON_STYLES[color]
          : "border-slate-700 bg-slate-800/60 text-slate-300 hover:bg-slate-800"
      }`}
    >
      <span className="flex items-center gap-2">
        {Icon && <Icon className="h-5 w-5" aria-hidden />}
        {label}
      </span>
      <span className="flex items-center gap-2 text-xs uppercase tracking-wider">
        {checked ? "On" : "Off"}
        <span
          className={`h-2.5 w-2.5 rounded-full ${checked ? DOT_STYLES[color] : "bg-slate-600"}`}
        />
      </span>
    </button>
  );
}
