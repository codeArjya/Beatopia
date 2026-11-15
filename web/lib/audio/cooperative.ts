import type { Op } from "../types/api";
import { allocatePcm, allocationBytes, frameRange, requireFinite, requireRange, secondsToFrame } from "./pcm";
import { AudioEngineError, SAMPLE_RATE, type PcmBuffer } from "./types";

const CHUNK = 65536;
/** Yield to browser paint/input after an 8 ms work budget; abort at every chunk. */
export class RenderWork {
  private lastYield = performance.now();
  constructor(private signal?: AbortSignal, private yieldTask = () => new Promise<void>((resolve) => setTimeout(resolve, 0))) {}
  check() { this.signal?.throwIfAborted(); }
  async checkpoint(force = false) {
    this.check();
    if (force || performance.now() - this.lastYield >= 8) {
      await this.yieldTask(); this.lastYield = performance.now(); this.check();
    }
  }
  async validate(pcm: PcmBuffer) {
    if (pcm.sampleRate !== SAMPLE_RATE) throw new AudioEngineError("bad_request", `Engine audio must use ${SAMPLE_RATE} Hz.`);
    const frames = pcm.channels[0]?.length ?? 0;
    allocationBytes(frames, pcm.channels.length);
    for (const channel of pcm.channels) {
      if (!(channel instanceof Float32Array) || channel.length !== frames) throw new AudioEngineError("bad_request", "PCM channels must be Float32Arrays of equal length.");
      for (let start = 0; start < frames; start += CHUNK) {
        await this.checkpoint();
        for (let i = start; i < Math.min(start + CHUNK, frames); i++) requireFinite(channel[i], "PCM sample");
      }
    }
  }
  async trim(pcm: PcmBuffer, start: number, end: number) {
    const [first, last] = frameRange(pcm, start, end);
    const result = allocatePcm(last - first, pcm.channels.length);
    for (let c = 0; c < result.channels.length; c++) for (let i = 0; i < last - first; i += CHUNK) {
      await this.checkpoint();
      result.channels[c].set(pcm.channels[c].subarray(first + i, Math.min(first + i + CHUNK, last)), i);
    }
    return result;
  }
  async pure(pcm: PcmBuffer, op: Extract<Op, { op: "reverse" | "gain" | "fade_in" | "fade_out" | "normalize" | "loop" }>) {
    let scale = 1, peak = 0, fadeFrames = 0, times = 1;
    if (op.op === "gain") { requireRange(op.db, -36, 12, "Gain (dB)"); scale = 10 ** (op.db / 20); }
    if (op.op === "fade_in" || op.op === "fade_out") {
      requireRange(op.ms, 0, 10_000, "Fade (ms)"); fadeFrames = Math.min(secondsToFrame(op.ms / 1000), pcm.channels[0].length);
    }
    if (op.op === "loop") {
      requireRange(op.times, 1, 16, "Loop count");
      if (!Number.isInteger(op.times)) throw new AudioEngineError("bad_request", "Loop count must be an integer.");
      times = op.times;
    }
    if (op.op === "normalize") {
      requireFinite(op.peak_db ?? -1, "Normalization peak (dB)"); scale = 10 ** ((op.peak_db ?? -1) / 20);
      if (!Number.isFinite(scale) || scale > 3.4028234663852886e38) throw new AudioEngineError("bad_request", "Normalization peak exceeds PCM capacity.");
      for (const channel of pcm.channels) for (let start = 0; start < channel.length; start += CHUNK) {
        await this.checkpoint();
        for (let i = start; i < Math.min(start + CHUNK, channel.length); i++) peak = Math.max(peak, Math.abs(channel[i]));
      }
    }
    const frames = pcm.channels[0].length;
    const result = allocatePcm(frames * times, pcm.channels.length);
    for (let c = 0; c < result.channels.length; c++) for (let start = 0; start < result.channels[c].length; start += CHUNK) {
      await this.checkpoint();
      const input = pcm.channels[c], output = result.channels[c];
      const end = Math.min(start + CHUNK, output.length);
      // Dispatch once per chunk. Validated finite input stays finite under reverse,
      // copy, fades and bounded normalization; gain alone can overflow Float32.
      switch (op.op) {
        case "reverse":
          for (let i = start; i < end; i++) output[i] = input[frames - 1 - i];
          break;
        case "gain":
          for (let i = start; i < end; i++) { output[i] = input[i] * scale; requireFinite(output[i], "PCM sample"); }
          break;
        case "normalize":
          if (peak === 0) output.set(input.subarray(start, end), start);
          else for (let i = start; i < end; i++) output[i] = input[i] / peak * scale;
          break;
        case "loop":
          for (let offset = start; offset < end;) {
            const first = offset % frames, count = Math.min(end - offset, frames - first);
            output.set(input.subarray(first, first + count), offset); offset += count;
          }
          break;
        default:
          for (let i = start; i < end; i++) {
            const distance = op.op === "fade_out" ? frames - 1 - i : i;
            output[i] = input[i] * (fadeFrames === 0 || distance >= fadeFrames ? 1 : fadeFrames === 1 ? 0 : distance / (fadeFrames - 1));
          }
      }
    }
    return result;
  }
  async concatenate(buffers: readonly PcmBuffer[], minimumChannels: 1 | 2) {
    const result = allocatePcm(buffers.reduce((sum, pcm) => sum + pcm.channels[0].length, 0),
      Math.max(minimumChannels, ...buffers.map((pcm) => pcm.channels.length)));
    let offset = 0;
    for (const pcm of buffers) {
      for (let c = 0; c < result.channels.length; c++) for (let i = 0; i < pcm.channels[0].length; i += CHUNK) {
        await this.checkpoint();
        result.channels[c].set((pcm.channels[c] ?? pcm.channels[0]).subarray(i, i + CHUNK), offset + i);
      }
      offset += pcm.channels[0].length;
    }
    return result;
  }
}
