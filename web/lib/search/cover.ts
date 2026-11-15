import type { Result } from "@/lib/types/api";

/** Cover art the site looks for in public/covers. Files that are missing are simply not used. */
export const COVER_FILES: readonly string[] = Array.from({ length: 6 }, (_, i) => `/covers/cover${i}.jpg`);

/**
 * What each cover was made for, in file order: dusty keys, night chords, a basement kick loop, sub bass,
 * a tape-room break, a glass pad. A result whose stem or tags match one of these gets that cover.
 */
const COVER_HINTS: readonly (readonly string[])[] = [
  ["keys", "piano", "rhodes", "organ", "wurlitzer"],
  ["chord", "guitar", "jazz", "soul"],
  ["drum", "kick", "percussion", "snare"],
  ["bass", "sub", "808"],
  ["break", "tape", "lofi", "lo-fi", "vinyl"],
  ["pad", "synth", "ambient", "strings", "texture"],
];

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function matchCover(text: string): number {
  const lower = text.toLowerCase();
  return COVER_HINTS.findIndex((hints) => hints.some((hint) => lower.includes(hint)));
}

/**
 * Picks a cover for a search result out of the covers that exist. The stem decides first (a drums stem gets
 * the kick-loop cover), then the first tag that matches, and otherwise the track id picks one, so the same
 * track always shows the same cover. Returns null when there are no covers.
 */
export function pickCover(result: Pick<Result, "stem" | "tags" | "track">, covers: readonly string[]): string | null {
  if (covers.length === 0) return null;
  for (const text of [result.stem, ...result.tags]) {
    const index = matchCover(text);
    if (index >= 0 && covers.includes(COVER_FILES[index])) return COVER_FILES[index];
  }
  return covers[hash(result.track.id) % covers.length];
}
