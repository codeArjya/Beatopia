import type { Slice } from "../types/api";
import { duration, requireRange, secondsToFrame, validatePcm } from "./pcm";
import { AudioEngineError, SAMPLE_RATE, type PcmBuffer } from "./types";

export interface SliceContext {
  /** Beats already mapped into the current clip's time coordinates. */
  readonly beatTimes?: readonly number[];
  readonly bpm?: number | null;
}

export type SliceOptions = Pick<Slice, "count" | "at" | "snap">;

/** Returns interior frame indices. Explicit cuts are exact; count cuts may snap. */
export function resolveCuts(pcm: PcmBuffer, options: SliceOptions, context: SliceContext = {}): number[] {
  validatePcm(pcm);
  const frames = pcm.channels[0].length;
  const hasCount = options.count != null;
  const hasAt = options.at != null;
  if (hasCount === hasAt) {
    throw new AudioEngineError("bad_request", "Specify exactly one of slice count or cut times.");
  }
  let cuts: number[];
  if (hasAt) {
    if (options.at!.length < 1 || options.at!.length > 31) {
      throw new AudioEngineError("bad_request", "Specify between 1 and 31 cut times.");
    }
    cuts = options.at!.map((time) => {
      requireRange(time, 0, duration(pcm), "Cut time");
      return secondsToFrame(time);
    });
  } else {
    const count = options.count!;
    requireRange(count, 2, 32, "Slice count");
    if (!Number.isInteger(count)) throw new AudioEngineError("bad_request", "Slice count must be an integer.");
    const snap = options.snap ?? "beat";
    if (snap !== "none" && snap !== "beat") {
      throw new AudioEngineError("bad_request", "Transient snapping requires onset detection.");
    }
    let beats: number[] = [];
    if (snap === "beat") {
      if (context.bpm == null || !Number.isFinite(context.bpm) || context.bpm <= 0) {
        throw new AudioEngineError("bad_request", "Beat snapping requires a known BPM.");
      }
      beats = (context.beatTimes ?? []).map(secondsToFrame).filter((frame) => frame > 0 && frame < frames);
      beats = [...new Set(beats)].sort((a, b) => a - b);
      if (beats.length === 0) throw new AudioEngineError("bad_request", "No interior beats are available for snapping.");
    }
    cuts = Array.from({ length: count - 1 }, (_, index) => {
      const target = frames * (index + 1) / count;
      // Sorted candidates and strict comparison select the earlier beat on ties.
      return snap === "none" ? Math.round(target) : beats.reduce((best, beat) =>
        Math.abs(beat - target) < Math.abs(best - target) ? beat : best,
      );
    });
  }
  let previous = 0;
  for (const cut of cuts) {
    if (cut <= previous || cut >= frames) {
      throw new AudioEngineError("bad_request", "Cuts must be sorted, unique and inside the clip; snapping must preserve the slice count.");
    }
    previous = cut;
  }
  return cuts;
}

export function slice(pcm: PcmBuffer, options: SliceOptions, context: SliceContext = {}): PcmBuffer[] {
  const boundaries = [0, ...resolveCuts(pcm, options, context), pcm.channels[0].length];
  return boundaries.slice(0, -1).map((start, index) => ({
    sampleRate: SAMPLE_RATE,
    channels: pcm.channels.map((channel) => channel.slice(start, boundaries[index + 1])),
  }));
}

/** Translate absolute track beats to a source window; never parse a window ID. */
export function mapBeatTimes(beatTimes: readonly number[], start: number, end: number): number[] {
  requireRange(start, 0, Number.MAX_SAFE_INTEGER / SAMPLE_RATE, "Source start");
  requireRange(end, start, Number.MAX_SAFE_INTEGER / SAMPLE_RATE, "Source end");
  for (const beat of beatTimes) requireRange(beat, 0, Number.MAX_SAFE_INTEGER / SAMPLE_RATE, "Beat time");
  return [...new Set(beatTimes.filter((beat) => beat >= start && beat < end).map((beat) => beat - start))]
    .sort((a, b) => a - b);
}
