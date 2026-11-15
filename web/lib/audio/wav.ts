import { validatePcm } from "./pcm";
import { SAMPLE_RATE, type PcmBuffer } from "./types";

export function exportFilename(metadata: { title: string; bpm?: number | null; key?: string | null }): string {
  const safe = (value: string) => value.replace(/[<>:"/\\|?*\x00-\x1f]/g, "-").replace(/[. ]+$/g, "").slice(0, 100) || "unknown";
  return `${safe(metadata.title)}-${metadata.bpm ?? "unknown"}bpm-${safe(metadata.key ?? "unknown")}.wav`;
}

/** 44.1 kHz, signed 16-bit little-endian, interleaved PCM RIFF/WAVE. */
export function encodeWav(pcm: PcmBuffer): ArrayBuffer {
  validatePcm(pcm);
  const channels = pcm.channels.length;
  const frames = pcm.channels[0].length;
  const blockAlign = channels * 2;
  const dataBytes = frames * blockAlign;
  const buffer = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(buffer);
  const text = (offset: number, value: string) => {
    for (let index = 0; index < value.length; index++) view.setUint8(offset + index, value.charCodeAt(index));
  };
  text(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, SAMPLE_RATE, true);
  view.setUint32(28, SAMPLE_RATE * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, dataBytes, true);
  let offset = 44;
  for (let frame = 0; frame < frames; frame++) {
    for (const channel of pcm.channels) {
      const sample = Math.max(-1, Math.min(1, channel[frame]));
      view.setInt16(offset, Math.round(sample * (sample < 0 ? 32768 : 32767)), true);
      offset += 2;
    }
  }
  return buffer;
}
