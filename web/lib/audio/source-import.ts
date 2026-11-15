import type { ClipSource, Stem, TrackDetail } from "../types/api";
import { fromAudioBuffer, loadSource } from "./decode";
import type { SourceAsset } from "./evaluate";
import { duration } from "./pcm";
import { SAMPLE_RATE } from "./types";

export const MAX_LOCAL_BYTES = 25 * 1024 * 1024;
export const LOCAL_ACCEPT = ".wav,.mp3,.flac,.m4a,.ogg";
export interface LoadedSource { source: ClipSource; asset: SourceAsset }

export function coveringStems(stems: readonly Stem[], trackId: string, start: number, end: number): Stem[] {
  const smallest = new Map<Stem["stem"], Stem>();
  for (const stem of stems) {
    if (stem.track_id !== trackId || stem.stem === "mix" || !stem.url ||
      !Number.isFinite(stem.range_start_s) || !Number.isFinite(stem.range_end_s) ||
      stem.range_start_s < 0 || stem.range_start_s > start || stem.range_end_s < end) continue;
    const previous = smallest.get(stem.stem);
    if (!previous || stem.range_end_s - stem.range_start_s < previous.range_end_s - previous.range_start_s) smallest.set(stem.stem, stem);
  }
  return [...smallest.values()];
}

export async function loadStem(stem: Stem, detail: TrackDetail, start: number, end: number, signal: AbortSignal): Promise<LoadedSource> {
  if (!(start >= 0 && end > start && end <= detail.track.duration_s) ||
    !coveringStems([stem], detail.track.id, start, end).length) throw new Error("This stem does not cover the requested track range.");
  const source: ClipSource = { track_id: detail.track.id, stem: stem.stem, audio_url: stem.url, start_s: start, end_s: end };
  const pcm = await loadSource(source, stem.range_start_s, signal);
  return { source, asset: { pcm, origin: start, beatTimes: detail.beat_times, bpm: detail.track.bpm ?? null, metadata: detail.track } };
}

/** No upload. A temporary blob identity is revoked after decode; replay owns PCM. */
export async function loadLocalFile(file: File, signal: AbortSignal): Promise<LoadedSource> {
  if (!/\.(wav|mp3|flac|m4a|ogg)$/i.test(file.name)) throw new Error("Choose a WAV, MP3, FLAC, M4A or OGG file.");
  if (!file.size || file.size > MAX_LOCAL_BYTES) throw new Error("Choose a nonempty audio file of at most 25 MB.");
  signal.throwIfAborted();
  const url = URL.createObjectURL(file);
  try {
    const bytes = await file.arrayBuffer();
    signal.throwIfAborted();
    const decoder = new OfflineAudioContext(2, 1, SAMPLE_RATE);
    let decoded: AudioBuffer;
    try { decoded = await decoder.decodeAudioData(bytes); }
    catch { signal.throwIfAborted(); throw new Error("This audio file is corrupt or unsupported by this browser. Try a WAV file."); }
    signal.throwIfAborted();
    // Preflights the 60-second / mono-stereo limits before copying channel arrays.
    const pcm = fromAudioBuffer(decoded);
    return { source: { track_id: "local", stem: "mix", audio_url: url, start_s: 0, end_s: duration(pcm) },
      asset: { pcm, origin: 0, bpm: null, beatTimes: [], metadata: {
        title: file.name.replace(/\.[^.]+$/, ""), license: "Local file — license not supplied", attribution: "Attribution not supplied",
      } } };
  } finally { URL.revokeObjectURL(url); }
}
