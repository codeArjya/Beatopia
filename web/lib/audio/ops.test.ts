import { describe, expect, it } from "vitest";
import { fadeIn, fadeOut, gain, loop, normalize, reverse, trim } from "./ops";
import { allocatePcm } from "./pcm";
import { SAMPLE_RATE, type PcmBuffer } from "./types";

const pcm = (...channels: number[][]): PcmBuffer => ({
  sampleRate: SAMPLE_RATE, channels: channels.map((channel) => new Float32Array(channel)),
});
const samples = (buffer: PcmBuffer) => buffer.channels.map((channel) => [...channel]);

describe("pure PCM operations", () => {
  it("trims half-open ranges on every channel, relative to the current buffer", () => {
    const input = pcm([1, 2, 3, 4, 5], [-1, -2, -3, -4, -5]);
    const first = trim(input, 1 / SAMPLE_RATE, 5 / SAMPLE_RATE);
    expect(samples(trim(first, 1 / SAMPLE_RATE, 3 / SAMPLE_RATE))).toEqual([[3, 4], [-3, -4]]);
    expect(() => trim(input, 0, 0.4 / SAMPLE_RATE)).toThrow();
    expect(() => trim(input, 3 / SAMPLE_RATE, 2 / SAMPLE_RATE)).toThrow();
    expect(() => trim(input, 0, 6 / SAMPLE_RATE)).toThrow();
  });

  it("reverses exact samples independently on both channels", () => {
    const input = pcm([0.25, 0, -1], [0.5, -0.5, 1]);
    expect(samples(reverse(input))).toEqual([[-1, 0, 0.25], [1, -0.5, 0.5]]);
    expect(samples(reverse(reverse(input)))).toEqual(samples(input));
  });

  it("uses dB amplitude gain without premature saturation", () => {
    const result = gain(pcm([0.5, -0.5, 0]), 20 * Math.log10(3));
    expect(samples(result)).toEqual([[1.5, -1.5, 0]]);
    expect(() => gain(result, 13)).toThrow();
    expect(() => gain(result, -37)).toThrow();
    expect(() => gain(result, NaN)).toThrow();
  });

  it("uses linear fade endpoints, clamps long fades and handles zero/one frame", () => {
    const input = pcm([1, 1, 1, 1, 1, 1]);
    const fourFramesMs = 4000 / SAMPLE_RATE;
    const fadedIn = samples(fadeIn(input, fourFramesMs))[0];
    expect(fadedIn[0]).toBe(0);
    expect(fadedIn[1]).toBeCloseTo(1 / 3);
    expect(fadedIn[2]).toBeCloseTo(2 / 3);
    expect(fadedIn.slice(3)).toEqual([1, 1, 1]);
    expect(samples(fadeOut(input, fourFramesMs))[0]).toEqual([...fadedIn].reverse());
    expect(samples(fadeIn(input, 0))).toEqual(samples(input));
    expect(samples(fadeIn(pcm([1]), 1))).toEqual([[0]]);
    expect(samples(fadeOut(pcm([1]), 1))).toEqual([[0]]);
    expect(samples(fadeOut(pcm([1, 1]), 1000))).toEqual([[1, 0]]);
    expect(samples(fadeIn(allocatePcm(0), 10))).toEqual([[]]);
    expect(() => fadeOut(input, -1)).toThrow();
    expect(() => fadeIn(input, 10_001)).toThrow();
  });

  it("preserves operation order", () => {
    const input = pcm([1, 1, 1]);
    expect(samples(reverse(fadeIn(input, 1000)))).toEqual([[1, 0.5, 0]]);
    expect(samples(fadeIn(reverse(input), 1000))).toEqual([[0, 0.5, 1]]);
  });

  it("normalizes using a shared stereo peak while leaving silence finite", () => {
    expect(samples(normalize(pcm([0.25, -0.5], [0.125, -0.25]), 0))).toEqual([[0.5, -1], [0.25, -0.5]]);
    expect(samples(normalize(pcm([0, 0], [0, 0])))).toEqual([[0, 0], [0, 0]]);
    expect(samples(normalize(allocatePcm(0)))).toEqual([[]]);
    expect(normalize(pcm([0.5])).channels[0][0]).toBeCloseTo(10 ** (-1 / 20));
    expect(() => normalize(pcm([1]), Infinity)).toThrow();
    expect(() => normalize(pcm([1]), 1000)).toThrow();
  });

  it("loops all samples with exact length and rejects excessive output", () => {
    expect(samples(loop(pcm([0.5, -1], [0, 1]), 3))).toEqual([
      [0.5, -1, 0.5, -1, 0.5, -1], [0, 1, 0, 1, 0, 1],
    ]);
    expect(() => loop(pcm([1]), 0)).toThrow();
    expect(() => loop(pcm([1]), 17)).toThrow();
    expect(() => loop(pcm([1]), 1.5)).toThrow();
    expect(() => loop(allocatePcm(SAMPLE_RATE * 31), 2)).toThrow(expect.objectContaining({ code: "range_too_long" }));
  });

  it("never mutates or aliases inputs, including no-op operations", () => {
    const input = pcm([0.25, -0.5, 1], [-0.25, 0.5, -1]);
    const original = samples(input);
    const outputs = [trim(input, 0, 3 / SAMPLE_RATE), reverse(input), gain(input, 0), fadeIn(input, 0),
      fadeOut(input, 0), normalize(input, 0), loop(input, 1)];
    outputs.forEach((output) => output.channels.forEach((channel) => channel.fill(7)));
    expect(samples(input)).toEqual(original);
  });
});
