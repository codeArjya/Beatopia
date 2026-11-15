// Pure timing helpers for the shared preview player (no DOM), so the loop boundary is unit-testable.

/** What to play: a [start, end] window (seconds, in file time) of one audio file. `id` identifies the caller (a card or a stem row). */
export type PreviewItem = { id: string; url: string; start: number; end: number };

/**
 * Wrap a little before `end`: rAF ticks every ~16 ms, so checking `t >= end` exactly would overshoot by up to a frame.
 * One frame early is inaudible on a 4–16 bar window.
 */
export const LOOP_LOOKAHEAD_S = 1 / 60;

/** Below `start` by more than this (a stray seek, or the browser restarting the file) counts as out of window. */
export const LOOP_BEFORE_TOLERANCE_S = 0.05;

/**
 * Where to seek, given the current position inside a looping window, or `null` to keep playing.
 * Returns `start` when the playhead reached the end (minus the lookahead) or is clearly before the window.
 * A window shorter than the lookahead never wraps on lookahead alone (only once `t >= end`).
 */
export function loopSeekTarget(t: number, start: number, end: number, lookahead = LOOP_LOOKAHEAD_S): number | null {
  if (!Number.isFinite(t) || end <= start) return null;
  const boundary = end - lookahead > start ? end - lookahead : end;
  if (t >= boundary) return start;
  if (t < start - LOOP_BEFORE_TOLERANCE_S) return start;
  return null;
}

/** Playhead position inside the window as a fraction in [0, 1] (for the waveform overlay). */
export function windowProgress(t: number, start: number, end: number): number {
  if (!Number.isFinite(t) || end <= start) return 0;
  return Math.min(1, Math.max(0, (t - start) / (end - start)));
}
