// "Flip this sample": up to 4 short, concrete ideas for a result, drawn from its why note (the advice sentences
// Gemini already wrote) plus its own tempo, key, length and stem. Pure, offline, no extra API call.

import type { Result } from "@/lib/types/api";

export const MAX_TIPS = 4;
const MAX_NOTE_TIPS = 2;

export type FlipTip = { kind: "note" | "tempo" | "key" | "chop" | "stem"; text: string };

const ADVICE_START =
  /^(try|chop|slice|pitch|repitch|loop|layer|add|filter|reverse|flip|stretch|use|pair|cut|drop|put|sample|run|boost|roll|swap|speed|slow|isolate|take|grab|stack|mute|let)\b/i;

/** Sentences of the note that read like advice ("Try …", "Chop …"), in order, at most MAX_NOTE_TIPS. */
export function adviceFromNote(note: string | null | undefined): string[] {
  if (!note) return [];
  const sentences = note
    .replace(/\s+/g, " ")
    .split(/(?<=[.!?])\s+(?=[A-Z])/)
    .map((s) => s.trim())
    .filter(Boolean);
  return sentences.filter((s) => ADVICE_START.test(s)).slice(0, MAX_NOTE_TIPS);
}

const NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"] as const;
const FLAT_TO_SHARP: Record<string, string> = { Db: "C#", Eb: "D#", Gb: "F#", Ab: "G#", Bb: "A#" };

/** "A minor" → "C major", "C major" → "A minor". Null for anything it can't read. */
export function relativeKey(key: string | null | undefined): string | null {
  const m = /^([A-G][#b]?)\s+(major|minor)$/i.exec(key?.trim() ?? "");
  if (!m) return null;
  const root = FLAT_TO_SHARP[m[1]] ?? m[1].toUpperCase().replace("B#", "C");
  const i = NOTES.indexOf(root as (typeof NOTES)[number]);
  if (i < 0) return null;
  const minor = m[2].toLowerCase() === "minor";
  return minor ? `${NOTES[(i + 3) % 12]} major` : `${NOTES[(i + 9) % 12]} minor`;
}

/** BPM after repitching by `semitones` on a sampler (speed and pitch move together). */
export function repitchedBpm(bpm: number, semitones: number): number {
  return bpm * 2 ** (semitones / 12);
}

function tempoTip(bpm: number | null | undefined): FlipTip | null {
  if (bpm == null || !Number.isFinite(bpm) || bpm <= 0) return null;
  const b = Math.round(bpm);
  if (b >= 115) return { kind: "tempo", text: `Half-time it: at ${b} BPM it sits under a ${Math.round(b / 2)} BPM beat for a slower, heavier groove.` };
  if (b <= 80) return { kind: "tempo", text: `Double-time it: at ${b} BPM it rides a ${b * 2} BPM beat, or speed it up into a fresh pocket.` };
  const up = Math.round(repitchedBpm(bpm, 2));
  const down = Math.round(repitchedBpm(bpm, -3));
  return { kind: "tempo", text: `Repitch for a new feel: +2 semitones lands near ${up} BPM, −3 slows it to about ${down} BPM.` };
}

function keyTip(key: string | null | undefined): FlipTip | null {
  const rel = relativeKey(key);
  if (!rel || !key) return null;
  return { kind: "key", text: `It's in ${key}: bass lines and chords in ${rel} (its relative key) will sit right on top.` };
}

function chopTip(bars: Result["bars"]): FlipTip {
  if (bars >= 4) return { kind: "chop", text: `Chop the ${bars} bars into one-bar slices and resequence them; reverse one slice for a lift.` };
  return { kind: "chop", text: `Only ${bars} ${bars === 1 ? "bar" : "bars"}: loop it as the bed and chop the last beat for fills.` };
}

const STEM_NAME: Record<Result["stem"], string> = {
  mix: "full mix",
  drums: "drums",
  bass: "bass",
  vocals: "vocals",
  other: "keys and synths",
  piano: "piano",
  guitar: "guitar",
};

function stemTip(stem: Result["stem"]): FlipTip {
  if (stem === "mix") return { kind: "stem", text: "Open Stems to pull out just the drums or the keys before you chop." };
  return { kind: "stem", text: `This is already the isolated ${STEM_NAME[stem]} stem, so it layers over your own drums cleanly.` };
}

/** Up to MAX_TIPS tips: the note's own advice first, then tempo, key, chop and stem ideas. */
export function flipTips(note: string | null | undefined, r: Pick<Result, "bars" | "stem" | "track">): FlipTip[] {
  const tips: FlipTip[] = adviceFromNote(note).map((text) => ({ kind: "note", text }));
  const lower = (note ?? "").toLowerCase();
  const extra = [
    tempoTip(r.track.bpm),
    keyTip(r.track.key),
    // Skip ideas the note already gave.
    /\bchop|slice/.test(lower) ? null : chopTip(r.bars),
    r.stem !== "mix" && /\bisolated|stem\b/.test(lower) ? null : stemTip(r.stem),
  ];
  for (const t of extra) if (t && tips.length < MAX_TIPS) tips.push(t);
  return tips;
}
