import { describe, expect, it } from "vitest";
import { allocatePcm } from "./pcm";
import { concatenate } from "./render";
import { mapBeatTimes, resolveCuts, slice, type SliceOptions } from "./slice";
import { SAMPLE_RATE } from "./types";

describe("slicing", () => {
  it("conserves every frame and channel when equal parts need rounding", () => {
    for (const frames of [4, 7, 31, 101]) {
      const input = allocatePcm(frames, 2);
      input.channels[0].set(Array.from({ length: frames }, (_, i) => i));
      input.channels[1].set(Array.from({ length: frames }, (_, i) => -i));
      const children = slice(input, { count: 4, snap: "none" });
      expect(children).toHaveLength(4);
      expect(children.reduce((total, child) => total + child.channels[0].length, 0)).toBe(frames);
      expect(concatenate(children)).toEqual(input);
      children[0].channels[0][0] = 999;
      expect(input.channels[0][0]).toBe(0);
    }
  });

  it("maps nonzero source offsets and chooses the nearest beat, with earlier ties", () => {
    const pcm = allocatePcm(SAMPLE_RATE * 4);
    const beatTimes = mapBeatTimes([14, 10.5, 9, 12.5, 11.5, 10.5], 10, 14);
    expect(beatTimes).toEqual([0.5, 1.5, 2.5]);
    expect(resolveCuts(pcm, { count: 2 }, { bpm: 120, beatTimes })).toEqual([SAMPLE_RATE * 1.5]);
    expect(resolveCuts(pcm, { count: 2, snap: "beat" }, { bpm: 120, beatTimes: [1, 2.1, 3] }))
      .toEqual([92_610]);
  });

  it("uses explicit clip-relative cuts without changing them to a beat", () => {
    const input = allocatePcm(10);
    const children = slice(input, { at: [2 / SAMPLE_RATE, 7 / SAMPLE_RATE], snap: "beat" });
    expect(children.map((child) => child.channels[0].length)).toEqual([2, 5, 3]);
  });

  it("rejects malformed or collapsed cuts instead of silently reducing child count", () => {
    const input = allocatePcm(10);
    const invalid: SliceOptions[] = [
      {}, { count: 2, at: [1 / SAMPLE_RATE] }, { at: [] }, { at: [0] },
      { at: [10 / SAMPLE_RATE] }, { at: [2 / SAMPLE_RATE, 1 / SAMPLE_RATE] },
      { at: [1 / SAMPLE_RATE, 1.1 / SAMPLE_RATE] }, { at: [NaN] },
      { at: Array.from({ length: 32 }, (_, i) => (i + 1) / SAMPLE_RATE) },
      { count: 1, snap: "none" }, { count: 33, snap: "none" },
      { count: 2.5, snap: "none" }, { count: 16, snap: "none" }, { count: 2, snap: "transient" },
    ];
    invalid.forEach((options) => expect(() => resolveCuts(input, options)).toThrow());
    expect(() => resolveCuts(input, { count: 2, snap: "beat" }, { beatTimes: [2 / SAMPLE_RATE] })).toThrow(/BPM/);
    expect(() => resolveCuts(input, { count: 2 }, { bpm: 120 })).toThrow(/No interior beats/);
    expect(() => resolveCuts(input, { count: 4 }, { bpm: 120, beatTimes: [5 / SAMPLE_RATE] })).toThrow(/slice count/);
  });
});
