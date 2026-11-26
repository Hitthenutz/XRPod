// Selected-button colors for each accent. Written out in full so Tailwind
// keeps these classes when it builds the HUD.
const SELECTED = {
  sky: "border-sky-400/70 bg-sky-500/15 text-sky-200",
  orange: "border-orange-400/70 bg-orange-500/15 text-orange-200",
  teal: "border-teal-400/70 bg-teal-500/15 text-teal-200",
};

/**
 * A row of preset buttons, like the fan levels. Tapping one saves that value.
 */
export function LevelButtons({ label, levels, value, unit = "", accent = "sky", onSelect }) {
  return (
    <div role="radiogroup" aria-label={label} className="grid grid-cols-5 gap-2">
      {levels.map((level) => {
        const selected = value === level;
        return (
          <button
            key={level}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onSelect(level)}
            className={`flex min-h-12 items-center justify-center rounded-xl border px-2 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 ${
              selected
                ? SELECTED[accent]
                : "border-slate-700 bg-slate-800/60 text-slate-300 hover:bg-slate-800"
            }`}
          >
            {level}
            {unit}
          </button>
        );
      })}
    </div>
  );
}