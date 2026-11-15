import { AudioEngineError, MAX_DURATION_S, SAMPLE_RATE, type PcmBuffer } from "./types";

export function requireFinite(value: number, name: string): void {
  if (!Number.isFinite(value)) {
    throw new AudioEngineError("bad_request", `${name} must be finite.`);
  }
}

export function requireRange(value: number, min: number, max: number, name: string): void {
  requireFinite(value, name);
  if (value < min || value > max) {
    throw new AudioEngineError("bad_request", `${name} must be between ${min} and ${max}.`);
  }
}

/** Nearest frame, with half-frame ties rounded toward the later frame. */
export function secondsToFrame(seconds: number): number {
  requireRange(seconds, 0, Number.MAX_SAFE_INTEGER / SAMPLE_RATE, "Time");
  return Math.round(seconds * SAMPLE_RATE);
}

export function allocationBytes(frames: number, channelCount: number): number {
  if (!Number.isSafeInteger(frames) || frames < 0 || ![1, 2].includes(channelCount)) {
    throw new AudioEngineError("bad_request", "Use a nonnegative frame count and one or two channels.");
  }
  if (frames > SAMPLE_RATE * MAX_DURATION_S) {
    throw new AudioEngineError("range_too_long", `Audio must be at most ${MAX_DURATION_S} seconds.`);
  }
  return frames * channelCount * Float32Array.BYTES_PER_ELEMENT;
}

export function validatePcm(pcm: PcmBuffer): void {
  if (pcm.sampleRate !== SAMPLE_RATE) {
    throw new AudioEngineError("bad_request", `Engine audio must use ${SAMPLE_RATE} Hz.`);
  }
  const frames = pcm.channels[0]?.length ?? 0;
  allocationBytes(frames, pcm.channels.length);
  for (const channel of pcm.channels) {
    if (!(channel instanceof Float32Array) || channel.length !== frames) {
      throw new AudioEngineError("bad_request", "PCM channels must be Float32Arrays of equal length.");
    }
    for (const sample of channel) {
      requireFinite(sample, "PCM sample");
    }
  }
}

export function duration(pcm: PcmBuffer): number {
  return (pcm.channels[0]?.length ?? 0) / pcm.sampleRate;
}

export function allocatePcm(frames: number, channelCount = 1): PcmBuffer {
  allocationBytes(frames, channelCount);
  return {
    sampleRate: SAMPLE_RATE,
    channels: Array.from({ length: channelCount }, () => new Float32Array(frames)),
  };
}

export function copyPcm(pcm: PcmBuffer): PcmBuffer {
  validatePcm(pcm);
  return { sampleRate: SAMPLE_RATE, channels: pcm.channels.map((channel) => channel.slice()) };
}

/** Half-open, clip-relative range. Validation happens before rounding. */
export function frameRange(pcm: PcmBuffer, start: number, end: number): [number, number] {
  requireRange(start, 0, duration(pcm), "Range start");
  requireRange(end, 0, duration(pcm), "Range end");
  const first = secondsToFrame(start);
  const last = secondsToFrame(end);
  if (first >= last) {
    throw new AudioEngineError("bad_request", "Select a range containing at least one frame.");
  }
  return [first, last];
}
