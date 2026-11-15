import type { ClipSource } from "../types/api";
import { allocationBytes, secondsToFrame, validatePcm } from "./pcm";
import { AudioEngineError, SAMPLE_RATE, type PcmBuffer } from "./types";

export function fromAudioBuffer(buffer: AudioBuffer, start = 0, end = buffer.duration): PcmBuffer {
  const first = secondsToFrame(start), last = first + secondsToFrame(end - start);
  if (first >= last || last > buffer.length || buffer.sampleRate !== SAMPLE_RATE) {
    throw new AudioEngineError("bad_request", `The decoded 44100 Hz file does not cover the requested window.`);
  }
  allocationBytes(last - first, buffer.numberOfChannels);
  const pcm = { sampleRate: buffer.sampleRate, channels: Array.from({ length: buffer.numberOfChannels }, (_, index) =>
    buffer.getChannelData(index).slice(first, last)) };
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
  // Validate absolute/file-local mapping and bounded output before downloading or copying.
  secondsToFrame(source.start_s - origin);
  const frames = secondsToFrame(source.end_s - source.start_s);
  if (!frames) throw new AudioEngineError("bad_request", "Choose a nonempty audio window.");
  allocationBytes(frames, 2);
  let bytes: ArrayBuffer;
  try {
    const response = await fetch(source.audio_url, { signal, mode: "cors", credentials: "omit" });
    if (!response.ok) throw new Error(`Audio download failed (HTTP ${response.status}). Check that the audio object is public, then retry.`);
    bytes = await response.arrayBuffer();
  } catch (error) {
    signal.throwIfAborted();
    if (error instanceof TypeError) throw new Error("Audio download failed. Check your connection and the audio server's CORS settings, then retry.");
    throw error;
  }
  signal.throwIfAborted();
  const decoder = new OfflineAudioContext(2, 1, SAMPLE_RATE);
  let decoded: AudioBuffer;
  try { decoded = await decoder.decodeAudioData(bytes); }
  catch { signal.throwIfAborted(); throw new Error("Audio could not be decoded. The file may be corrupt or unsupported; check its format, then retry."); }
  signal.throwIfAborted();
  return fromAudioBuffer(decoded, source.start_s - origin, source.end_s - origin);
}
