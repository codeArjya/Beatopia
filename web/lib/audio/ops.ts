import { allocatePcm, frameRange, requireFinite, requireRange, secondsToFrame, validatePcm } from "./pcm";
import { AudioEngineError, SAMPLE_RATE, type PcmBuffer } from "./types";

export function trim(pcm: PcmBuffer, start: number, end: number): PcmBuffer {
  validatePcm(pcm);
  const [first, last] = frameRange(pcm, start, end);
  return { sampleRate: SAMPLE_RATE, channels: pcm.channels.map((channel) => channel.slice(first, last)) };
}

function mapSamples(pcm: PcmBuffer, transform: (sample: number, frame: number) => number): PcmBuffer {
  validatePcm(pcm);
  const result = { sampleRate: SAMPLE_RATE, channels: pcm.channels.map((channel) => channel.map(transform)) };
  validatePcm(result);
  return result;
}

export function reverse(pcm: PcmBuffer): PcmBuffer {
  validatePcm(pcm);
  return { sampleRate: SAMPLE_RATE, channels: pcm.channels.map((channel) => channel.slice().reverse()) };
}

export function gain(pcm: PcmBuffer, db: number): PcmBuffer {
  requireRange(db, -36, 12, "Gain (dB)");
  const scale = 10 ** (db / 20);
  return mapSamples(pcm, (sample) => sample * scale);
}

function fade(pcm: PcmBuffer, ms: number, out: boolean): PcmBuffer {
  requireRange(ms, 0, 10_000, "Fade (ms)");
  const frames = Math.min(secondsToFrame(ms / 1000), pcm.channels[0]?.length ?? 0);
  return mapSamples(pcm, (sample, index) => {
    const distance = out ? pcm.channels[0].length - 1 - index : index;
    // Zero duration is a no-op; a one-frame fade silences its endpoint.
    const scale = frames === 0 || distance >= frames ? 1 : frames === 1 ? 0 : distance / (frames - 1);
    return sample * scale;
  });
}

export function fadeIn(pcm: PcmBuffer, ms: number): PcmBuffer {
  return fade(pcm, ms, false);
}

export function fadeOut(pcm: PcmBuffer, ms: number): PcmBuffer {
  return fade(pcm, ms, true);
}

export function normalize(pcm: PcmBuffer, peakDb = -1): PcmBuffer {
  requireFinite(peakDb, "Normalization peak (dB)");
  const target = 10 ** (peakDb / 20);
  if (!Number.isFinite(target) || target > 3.4028234663852886e38) {
    throw new AudioEngineError("bad_request", "Normalization peak exceeds PCM capacity.");
  }
  validatePcm(pcm);
  let peak = 0;
  for (const channel of pcm.channels) {
    for (const sample of channel) peak = Math.max(peak, Math.abs(sample));
  }
  // One shared peak preserves the stereo balance; silence remains finite.
  return mapSamples(pcm, (sample) => peak === 0 ? sample : (sample / peak) * target);
}

export function loop(pcm: PcmBuffer, times: number): PcmBuffer {
  requireRange(times, 1, 16, "Loop count");
  if (!Number.isInteger(times)) throw new AudioEngineError("bad_request", "Loop count must be an integer.");
  validatePcm(pcm);
  const frames = pcm.channels[0].length;
  const result = allocatePcm(frames * times, pcm.channels.length);
  result.channels.forEach((channel, index) => {
    for (let repeat = 0; repeat < times; repeat++) channel.set(pcm.channels[index], repeat * frames);
  });
  return result;
}
