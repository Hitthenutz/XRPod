import { useEffect, useId, useRef, useState } from "react";

// Width of the thumb in index.css (1.75rem); the value maps across the track
// minus half a thumb at each end, like the native control.
const THUMB_PX = 28;

/**
 * Range slider that shows its value live while dragging and calls
 * `onCommit` once when the user lets go, so a drag produces one write and
 * one history entry rather than dozens.
 *
 * Pointer dragging is handled here rather than by the browser: the pointer
 * is captured on press and the value is computed from its X position, so the
 * thumb follows the mouse/finger exactly and the drag can't be cancelled by
 * the page scrolling. Keyboard input still uses the native control.
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
  const draftRef = useRef(value);
  const dragging = useRef(false);
  const inputRef = useRef(null);
  const latest = useRef({ value, onCommit });
  latest.current = { value, onCommit };

  const show = (next) => {
    draftRef.current = next;
    setDraft(next);
  };

  // Follow external updates (other devices) unless the user is mid-drag.
  useEffect(() => {
    if (!dragging.current) show(value);
  }, [value]);

  const commit = (next = draftRef.current) => {
    dragging.current = false;
    if (Number.isFinite(next) && next !== latest.current.value) {
      latest.current.onCommit(next);
    }
  };

  const valueAt = (clientX) => {
    const rect = inputRef.current.getBoundingClientRect();
    const usable = Math.max(1, rect.width - THUMB_PX);
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left - THUMB_PX / 2) / usable));
    const stepped = Math.round((ratio * (max - min)) / step) * step + min;
    return Math.min(max, Math.max(min, Number(stepped.toFixed(6))));
  };

  const onPointerDown = (e) => {
    if (disabled || (e.pointerType === "mouse" && e.button !== 0)) return;
    e.preventDefault(); // stop the browser's own drag handling
    const el = inputRef.current;
    try {
      el.setPointerCapture(e.pointerId);
    } catch {
      /* pointer already gone; the drag simply won't be captured */
    }
    el.focus({ preventScroll: true });
    dragging.current = true;
    show(valueAt(e.clientX));
  };

  const onPointerMove = (e) => {
    if (dragging.current) show(valueAt(e.clientX));
  };

  // Release, cancel and lost capture all end the drag; save where it stopped
  // so the slider never stays stuck in "dragging" and ignoring updates.
  const endDrag = () => {
    if (dragging.current) commit();
  };

  // Keyboard (arrows, Home/End, PageUp/Down) goes through the native
  // `change` event, which fires once the value is set.
  useEffect(() => {
    const el = inputRef.current;
    const onNativeChange = () => commit(Number(el.value));
    el.addEventListener("change", onNativeChange);
    return () => el.removeEventListener("change", onNativeChange);
  }, []);

  const pct = max > min ? ((draft - min) / (max - min)) * 100 : 0;

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
          if (!dragging.current) show(Number(e.target.value));
        }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onLostPointerCapture={endDrag}
        onKeyUp={() => commit(Number(inputRef.current.value))}
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
