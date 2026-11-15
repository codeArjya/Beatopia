import { validatePcm } from "./pcm";
import { SAMPLE_RATE, type PcmBuffer } from "./types";

const SIZE = 512;
const HOP = 256;

/** In-place radix-2 FFT magnitudes. Fixed windows bound analysis memory. */
function spectrum(real: Float64Array, imaginary: Float64Array, magnitudes: Float64Array) {
  for (let i = 1, j = 0; i < SIZE; i++) {
    let bit = SIZE >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) [real[i], real[j]] = [real[j], real[i]];
  }
  for (let width = 2; width <= SIZE; width *= 2) {
    const angle = -2 * Math.PI / width;
    for (let start = 0; start < SIZE; start += width) {
      for (let k = 0; k < width / 2; k++) {
        const cosine = Math.cos(angle * k), sine = Math.sin(angle * k);
        const a = start + k, b = a + width / 2;
        const re = real[b] * cosine - imaginary[b] * sine;
        const im = real[b] * sine + imaginary[b] * cosine;
        real[b] = real[a] - re; imaginary[b] = imaginary[a] - im;
        real[a] += re; imaginary[a] += im;
      }
    }
  }
  for (let bin = 0; bin < magnitudes.length; bin++) magnitudes[bin] = Math.hypot(real[bin], imaginary[bin]) / SIZE;
}

/** Positive spectral flux with local median threshold and 40 ms peak suppression.
 * RMS downmix avoids cancelling opposite-polarity stereo attacks. Returns current-clip seconds.
 */
export function detectOnsets(pcm: PcmBuffer): number[] {
  validatePcm(pcm);
  const frames = pcm.channels[0].length;
  const mono = new Float32Array(frames);
  for (let i = 0; i < frames; i++) {
    let energy = 0;
    for (const channel of pcm.channels) energy += channel[i] ** 2;
    mono[i] = Math.sqrt(energy / pcm.channels.length);
  }
  const real = new Float64Array(SIZE), imaginary = new Float64Array(SIZE);
  const previous = new Float64Array(SIZE / 2 + 1), magnitudes = new Float64Array(previous.length);
  const flux: number[] = [], peaks: number[] = [];
  for (let center = 0; center < frames; center += HOP) {
    let peak = center;
    for (let i = 0; i < SIZE; i++) {
      const frame = center - SIZE / 2 + i;
      const sample = mono[frame] ?? 0;
      real[i] = sample * (0.5 - 0.5 * Math.cos(2 * Math.PI * i / (SIZE - 1)));
      if (sample > (mono[peak] ?? 0)) peak = frame;
    }
    imaginary.fill(0);
    spectrum(real, imaginary, magnitudes);
    let value = 0;
    for (let bin = 1; bin < magnitudes.length; bin++) value += Math.max(0, magnitudes[bin] - previous[bin]);
    flux.push(value); peaks.push(peak);
    previous.set(magnitudes);
  }
  const maxFlux = flux.reduce((max, value) => Math.max(max, value), 0);
  const selected: number[] = [];
  for (let i = 1; i < flux.length - 1; i++) {
    const neighborhood = flux.slice(Math.max(0, i - 8), Math.min(flux.length, i + 9)).sort((a, b) => a - b);
    const threshold = Math.max(0.002, maxFlux * 0.08, neighborhood[Math.floor(neighborhood.length / 2)] * 3);
    if (flux[i] <= threshold || flux[i] < flux[i - 1] || flux[i] <= flux[i + 1]) continue;
    const frame = peaks[i];
    if (frame <= 0 || frame >= frames) continue;
    const last = selected[selected.length - 1];
    if (last != null && frame - last < SAMPLE_RATE * 0.04) continue;
    selected.push(frame);
  }
  return selected.map((frame) => frame / SAMPLE_RATE);
}
