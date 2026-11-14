// Browser-only: fetch + decode audio for mini waveforms.
// One shared OfflineAudioContext (decoding needs no user gesture, and an offline context never trips the
// autoplay warning). Decoded buffers are big (a 3-minute stereo track is ~60 MB), so only the last few are kept;
// the small per-window peaks are what TanStack Query caches long-term.

import { createLimiter, LruCache } from "./limit";

/** Real windows share their track's file, so a few buffers cover a page of results. */
const BUFFER_CACHE_SIZE = 3;
/** At most two fetch+decode jobs at once, so waveforms never starve the preview audio on slow Wi-Fi. */
const DECODE_CONCURRENCY = 2;
/** Skip waveforms for files bigger than this (the card shows the flat placeholder). */
const MAX_BYTES = 30 * 1024 * 1024;
const DECODE_SAMPLE_RATE = 44_100;

let ctx: OfflineAudioContext | null = null;
const buffers = new LruCache<string, Promise<AudioBuffer>>(BUFFER_CACHE_SIZE);
const limit = createLimiter(DECODE_CONCURRENCY);

function context(): OfflineAudioContext {
  ctx ??= new OfflineAudioContext(1, 1, DECODE_SAMPLE_RATE);
  return ctx;
}

/** Decoded audio for `url` (relative urls resolve against the page). Concurrent calls share one request. */
export function decodeAudio(url: string): Promise<AudioBuffer> {
  const key = new URL(url, window.location.href).href;
  const hit = buffers.get(key);
  if (hit) return hit;
  const p = limit(async () => {
    const res = await fetch(key);
    if (!res.ok) throw new Error(`waveform fetch ${res.status}`);
    const size = Number(res.headers.get("content-length"));
    if (size > MAX_BYTES) throw new Error(`waveform skipped: ${size} bytes`);
    return context().decodeAudioData(await res.arrayBuffer());
  });
  // A failure isn't cached, so a later mount can try again.
  p.catch(() => buffers.delete(key, p));
  buffers.set(key, p);
  return p;
}

/** Channel arrays of a decoded buffer, in the shape computePeaks takes. */
export function channelsOf(buffer: AudioBuffer): Float32Array[] {
  return Array.from({ length: buffer.numberOfChannels }, (_, i) => buffer.getChannelData(i));
}
