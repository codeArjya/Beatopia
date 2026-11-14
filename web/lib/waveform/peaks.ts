// Pure peak extraction for the result-card mini waveform (no DOM, unit-tested).

export const PEAK_BUCKETS = 96;

/** Decoded audio as plain arrays: what an AudioBuffer gives via getChannelData. */
export type PeakSource = { channels: ArrayLike<number>[]; sampleRate: number };

/**
 * Max absolute amplitude (over all channels) for `buckets` equal slices of [start, end] seconds.
 * The range is clamped to the audio; an empty range gives all zeros. Values are raw (0..1 for normal audio).
 */
export function computePeaks(src: PeakSource, start: number, end: number, buckets = PEAK_BUCKETS): number[] {
  const out = new Array<number>(buckets).fill(0);
  const length = src.channels.reduce((n, c) => Math.max(n, c.length), 0);
  if (!length || !(src.sampleRate > 0) || buckets <= 0) return out;
  const s0 = clamp(Math.floor(start * src.sampleRate), 0, length);
  const s1 = clamp(Math.ceil(end * src.sampleRate), 0, length);
  const n = s1 - s0;
  if (n <= 0) return out;

  for (let b = 0; b < buckets; b++) {
    const from = s0 + Math.floor((b * n) / buckets);
    // At least one sample per bucket, even when the window has fewer samples than buckets.
    const to = Math.max(from + 1, s0 + Math.floor(((b + 1) * n) / buckets));
    let peak = 0;
    for (const ch of src.channels) {
      const stop = Math.min(to, ch.length);
      for (let i = from; i < stop; i++) {
        const v = Math.abs(ch[i]);
        if (v > peak) peak = v;
      }
    }
    out[b] = peak;
  }
  return out;
}

/**
 * Scale peaks so the loudest bucket is 1, for drawing. `floor` caps the gain, so near-silence stays small
 * instead of being blown up into noise.
 */
export function normalizePeaks(peaks: readonly number[], floor = 0.1): number[] {
  const max = peaks.reduce((m, v) => (v > m ? v : m), 0);
  const ref = Math.max(max, floor);
  return peaks.map((v) => Math.min(1, v / ref));
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}
