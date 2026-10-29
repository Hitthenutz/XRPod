import { useEffect, useId, useRef, useState } from "react";

/**
 * Range slider that shows its value live while dragging and calls
 * `onCommit` once when the user lets go (pointer up / key up / blur), so a
 * drag produces one write and one history entry rather than dozens.
 */
export function Slider({
  label,
  value,
  min = 0,
  max = 100,
  step = 1,
  unit = "",
  accent = "sky",
  disabled = false,
  onCommit,
}) {
  const id = useId();
  const [draft, setDraft] = useState(value);
  const dragging = useRef(false);

  // Follow external updates (other devices) unless the user is mid-drag.
  useEffect(() => {
    if (!dragging.current) setDraft(value);
  }, [value]);

  const inputRef = useRef(null);
  const latest = useRef({ value, onCommit });
  latest.current = { value, onCommit };

  // Read the value off the element rather than from state, so a commit that
  // fires in the same tick as the last input event still sees it.
  const commit = () => {
    dragging.current = false;
    const next = Number(inputRef.current.value);
    if (next !== latest.current.value) latest.current.onCommit(next);
  };

  // The native `change` event fires once on release (React's onChange is
  // really `input`). Duplicate commits are harmless: applyChanges ignores
  // values that match the current state.
  useEffect(() => {
    const el = inputRef.current;
    el.addEventListener("change", commit);
    return () => el.removeEventListener("change", commit);
  }, []);

  const pct = ((draft - min) / (max - min)) * 100;

  return (
    <div className={disabled ? "opacity-50" : ""}>
      <div className="mb-2 flex items-baseline justify-between">
        <label htmlFor={id} className="text-sm text-slate-300">
          {label}
        </label>
        <span className="font-mono text-2xl font-semibold tabular-nums text-slate-50">
          {draft}
          <span className="ml-0.5 text-base text-slate-400">{unit}</span>
        </span>
      </div>
      <input
        ref={inputRef}
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={draft}
        disabled={disabled}
        onChange={(e) => {
          dragging.current = true;
          setDraft(Number(e.target.value));
        }}
        onPointerUp={commit}
        onKeyUp={commit}
        onBlur={() => dragging.current && commit()}
        className={`hud-range hud-range--${accent}`}
        style={{ "--fill": `${pct}%` }}
      />
      <div className="mt-1 flex justify-between text-xs text-slate-500">
        <span>
          {min}
          {unit}
        </span>
        <span>
          {max}
          {unit}
        </span>
      </div>
    </div>
  );
}
