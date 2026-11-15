import type { Op } from "../types/api";
import { allocationBytes, requireRange, validatePcm } from "./pcm";
import { AudioEngineError, type PcmBuffer } from "./types";

export type OfflineOp = Extract<Op, { op: "repitch" | "pitch_shift" | "stretch_to_bpm" | "filter" }>;
export interface OfflinePlan {
  readonly frames: number;
  readonly rate: number;
  readonly semitones: number;
  readonly granular: boolean;
}

/** Validate before allocating a browser context. Fits always use the original track BPM. */
export function planOfflineFrames(pcm: PcmBuffer, op: OfflineOp, bpm: number | null): OfflinePlan {
  validatePcm(pcm);
  let rate = 1;
  let semitones = 0;
  let granular = false;
  switch (op.op) {
    case "repitch":
    case "pitch_shift":
      requireRange(op.semitones, -24, 24, "Semitones");
      if (op.op === "repitch") rate = 2 ** (op.semitones / 12);
      else { semitones = op.semitones; granular = true; }
      break;
    case "stretch_to_bpm":
      requireRange(op.target_bpm, 40, 240, "Target BPM");
      if (bpm == null || !Number.isFinite(bpm) || bpm <= 0) {
        throw new AudioEngineError("bad_request", "Tempo fit requires a known source BPM.");
      }
      rate = op.target_bpm / bpm;
      granular = op.keep_pitch ?? false;
      break;
    case "filter":
      if (op.type !== "lowpass" && op.type !== "highpass") throw new AudioEngineError("bad_request", "Choose a low-pass or high-pass filter.");
      requireRange(op.freq_hz, 20, 20000, "Filter frequency");
      break;
  }
  const frames = Math.max(1, Math.round(pcm.channels[0].length / rate));
  allocationBytes(frames, pcm.channels.length);
  if (!pcm.channels[0].length) throw new AudioEngineError("bad_request", "Offline effects require nonempty audio.");
  return { frames, rate, semitones, granular };
}
