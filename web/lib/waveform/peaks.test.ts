import { describe, expect, it } from "vitest";

import { computePeaks, normalizePeaks, PEAK_BUCKETS } from "./peaks";

const SR = 100; // 100 samples per second keeps the arithmetic readable

describe("computePeaks", () => {
  it("returns PEAK_BUCKETS values by default", () => {
    const ch = new Float32Array(10 * SR).fill(0.5);
    const peaks = computePeaks({ channels: [ch], sampleRate: SR }, 0, 10);
    expect(peaks).toHaveLength(PEAK_BUCKETS);
    expect(peaks.every((p) => p === 0.5)).toBe(true);
  });

  it("only reads the [start, end] window", () => {
    const ch = new Float32Array(10 * SR);
    ch.fill(0.9, 0, 2 * SR); // loud before the window
    ch.fill(-0.25, 2 * SR, 4 * SR); // the window: negative values count by magnitude
    ch.fill(0.9, 4 * SR); // loud after the window
    const peaks = computePeaks({ channels: [ch], sampleRate: SR }, 2, 4, 4);
    expect(peaks).toEqual([0.25, 0.25, 0.25, 0.25]);
  });

  it("takes the max over channels and locates a transient in its bucket", () => {
    const left = new Float32Array(4 * SR);
    const right = new Float32Array(4 * SR);
    right[3 * SR + 10] = -0.8; // in the last of 4 one-second buckets
    left[10] = 0.3;
    const peaks = computePeaks({ channels: [left, right], sampleRate: SR }, 0, 4, 4);
    expect(peaks[0]).toBeCloseTo(0.3);
    expect(peaks[1]).toBe(0);
    expect(peaks[2]).toBe(0);
    expect(peaks[3]).toBeCloseTo(0.8);
  });

  it("clamps a window that runs past the file end", () => {
    const ch = new Float32Array(2 * SR).fill(0.4);
    const peaks = computePeaks({ channels: [ch], sampleRate: SR }, 1, 16, 8);
    expect(peaks[0]).toBeCloseTo(0.4);
    expect(peaks.at(-1)).toBeCloseTo(0.4);
  });

  it("gives zeros for an empty or inverted range, or no audio", () => {
    const ch = new Float32Array(SR).fill(1);
    expect(computePeaks({ channels: [ch], sampleRate: SR }, 5, 6, 3)).toEqual([0, 0, 0]);
    expect(computePeaks({ channels: [ch], sampleRate: SR }, 0.5, 0.2, 3)).toEqual([0, 0, 0]);
    expect(computePeaks({ channels: [], sampleRate: SR }, 0, 1, 2)).toEqual([0, 0]);
  });

  it("fills every bucket when the window has fewer samples than buckets", () => {
    const ch = new Float32Array([0.1, 0.2, 0.3]);
    const peaks = computePeaks({ channels: [ch], sampleRate: 1 }, 0, 3, 6);
    expect(peaks.every((p) => p > 0)).toBe(true);
  });
});

describe("normalizePeaks", () => {
  it("scales the loudest bucket to 1", () => {
    expect(normalizePeaks([0.25, 0.5, 0.125])).toEqual([0.5, 1, 0.25]);
  });

  it("does not blow up near-silence past the floor", () => {
    const [a, b] = normalizePeaks([0.01, 0.02], 0.1);
    expect(a).toBeCloseTo(0.1);
    expect(b).toBeCloseTo(0.2);
    expect(normalizePeaks([0, 0])).toEqual([0, 0]);
  });
});
