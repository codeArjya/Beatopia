import type { ClipSource } from "../types/api";
import { secondsToFrame, validatePcm } from "./pcm";
import { AudioEngineError, SAMPLE_RATE, type PcmBuffer } from "./types";

export function fromAudioBuffer(buffer: AudioBuffer, start = 0, end = buffer.duration): PcmBuffer {
  const pcm = { sampleRate: buffer.sampleRate, channels: Array.from({ length: buffer.numberOfChannels }, (_, index) =>
    buffer.getChannelData(index).slice(secondsToFrame(start), secondsToFrame(end))) };
  if (start < 0 || end > buffer.duration || secondsToFrame(start) >= secondsToFrame(end)) {
    throw new AudioEngineError("bad_request", "The decoded file does not cover the requested window.");
  }
  validatePcm(pcm);
  return pcm;
}
export function toAudioBuffer(context: BaseAudioContext, pcm: PcmBuffer): AudioBuffer {
  const buffer = context.createBuffer(pcm.channels.length, pcm.channels[0].length, SAMPLE_RATE);
  pcm.channels.forEach((channel, index) => buffer.copyToChannel(new Float32Array(channel), index));
  return buffer;
}
/** Decode offline (no autoplay context), resample to 44100, retain only the bounded window. */
export async function loadSource(source: ClipSource, origin: number, signal: AbortSignal): Promise<PcmBuffer> {
  const response = await fetch(source.audio_url, { signal });
  if (!response.ok) throw new Error(`Audio download failed (${response.status}). Retry or use fixture mode.`);
  const bytes = await response.arrayBuffer();
  signal.throwIfAborted();
  const decoder = new OfflineAudioContext(2, 1, SAMPLE_RATE);
  let decoded: AudioBuffer;
  try { decoded = await decoder.decodeAudioData(bytes); }
  catch { throw new Error("Audio could not be decoded. Check the audio URL/CORS settings, then retry or use fixture mode."); }
  signal.throwIfAborted();
  return fromAudioBuffer(decoded, source.start_s - origin, source.end_s - origin);
}
