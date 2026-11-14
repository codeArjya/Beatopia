import type { ClipSource, StemName, TrackDetail } from "../types/api";
import { AudioEngineError, MAX_DURATION_S } from "./types";

const stems: StemName[] = ["mix", "vocals", "drums", "bass", "other", "guitar", "piano"];
export interface EditorEntry { trackId: string; start: number; end: number; stem: StemName }
export function parseEntry(params: Pick<URLSearchParams, "get">): EditorEntry {
  const trackId = params.get("track")?.trim();
  const startText = params.get("start");
  const endText = params.get("end");
  const stem = params.get("stem") ?? "mix";
  const start = Number(startText);
  const end = Number(endText);
  if (!trackId) throw new AudioEngineError("bad_request", "No track selected. Open a sample from search or the fixture link below.");
  if (!startText?.trim() || !endText?.trim() || !Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start) {
    throw new AudioEngineError("bad_request", "Supply a valid start and end in seconds, with end after start.");
  }
  if (end - start > MAX_DURATION_S) throw new AudioEngineError("range_too_long", "Choose a window of at most 60 seconds.");
  if (!stems.includes(stem as StemName)) throw new AudioEngineError("bad_request", "Unknown stem. Choose mix or an available stem.");
  return { trackId, start, end, stem: stem as StemName };
}
export function resolveEntry(entry: EditorEntry, detail: TrackDetail): { source: ClipSource; origin: number; windowId?: string } {
  if (detail.track.id !== entry.trackId) throw new AudioEngineError("bad_request", "This track is not available in the current fixture library.");
  if (entry.end > detail.track.duration_s) throw new AudioEngineError("bad_request", "The requested window extends beyond the track.");
  const stem = entry.stem === "mix" ? null : detail.stems.find((item) =>
    item.stem === entry.stem && item.range_start_s <= entry.start && item.range_end_s >= entry.end);
  if (entry.stem !== "mix" && !stem) throw new AudioEngineError("bad_request", "This stem is not ready for the requested range. Choose mix.");
  return {
    source: { track_id: entry.trackId, stem: entry.stem, audio_url: stem?.url ?? detail.audio_url,
      start_s: entry.start, end_s: entry.end },
    origin: stem?.range_start_s ?? 0,
    windowId: detail.windows.find((window) => window.stem === entry.stem && window.start_s === entry.start && window.end_s === entry.end)?.id,
  };
}
