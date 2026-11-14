import { allocatePcm, validatePcm } from "./pcm";
import type { PcmBuffer } from "./types";

/** Concatenate occurrences without gaps; mono is duplicated when stereo is needed. */
export function concatenate(buffers: readonly PcmBuffer[], minimumChannels: 1 | 2 = 1): PcmBuffer {
  buffers.forEach(validatePcm);
  const frames = buffers.reduce((total, pcm) => total + pcm.channels[0].length, 0);
  const channelCount = Math.max(minimumChannels, ...buffers.map((pcm) => pcm.channels.length));
  const result = allocatePcm(frames, channelCount);
  let offset = 0;
  for (const pcm of buffers) {
    result.channels.forEach((channel, index) => channel.set(pcm.channels[index] ?? pcm.channels[0], offset));
    offset += pcm.channels[0].length;
  }
  return result;
}
