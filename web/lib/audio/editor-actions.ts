import type { Op } from "../types/api";

/** Index addresses an occurrence, including when the same leaf appears twice. */
export function arrangeOccurrence(order: readonly string[], index: number, action: "duplicate" | "left" | "right"): Op[] {
  if (index < 0 || index >= order.length) return [];
  const next = [...order];
  if (action === "duplicate") next.splice(index + 1, 0, order[index]);
  else {
    const destination = index + (action === "left" ? -1 : 1);
    if (destination < 0 || destination >= order.length) return [];
    [next[index], next[destination]] = [next[destination], next[index]];
  }
  return [{ op: "arrange", order: next }];
}

export function describeOp(op: Op): string {
  switch (op.op) {
    case "arrange": return `Arrange ${op.order.join(" → ")}`;
    case "slice": return `Chop ${op.clip} into ${op.count ?? (op.at?.length ?? 0) + 1}`;
    case "reverse": return `Reverse ${op.clip}`;
    case "repitch": return `Repitch ${op.clip} ${op.semitones > 0 ? "+" : ""}${op.semitones} semitones`;
    case "pitch_shift": return `Pitch shift ${op.clip} ${op.semitones} semitones`;
    case "trim": return `Trim ${op.clip} to ${op.start_s.toFixed(3)}–${op.end_s.toFixed(3)} s`;
    case "stretch_to_bpm": return `Fit ${op.clip} to ${op.target_bpm} BPM`;
    case "gain": return `Gain ${op.clip} ${op.db} dB`;
    case "fade_in": return `Fade in ${op.clip} ${op.ms} ms`;
    case "fade_out": return `Fade out ${op.clip} ${op.ms} ms`;
    case "normalize": return `Normalize ${op.clip}`;
    case "loop": return `Loop ${op.clip} ×${op.times}`;
    case "filter": return `${op.type === "lowpass" ? "Low-pass" : "High-pass"} ${op.clip} ${op.freq_hz} Hz`;
  }
}

export type EditorShortcut = "play" | "slice" | "reverse" | "up" | "down" | "undo" | "redo" | "export";
export function editorShortcut(event: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "shiftKey" | "altKey" | "repeat" | "isComposing">, typing: boolean): EditorShortcut | null {
  if (typing || event.repeat || event.isComposing || event.altKey) return null;
  const key = event.key.toLowerCase();
  if (event.ctrlKey || event.metaKey) return key === "z" ? event.shiftKey ? "redo" : "undo" : null;
  if (event.shiftKey) return null;
  const bindings: Partial<Record<string, EditorShortcut>> = { " ": "play", s: "slice", r: "reverse", arrowup: "up", arrowdown: "down", e: "export" };
  return bindings[key] ?? null;
}
