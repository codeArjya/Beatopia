import { describe, expect, it } from "vitest";
import { allocatePcm, allocationBytes, copyPcm, duration, secondsToFrame, validatePcm } from "./pcm";
import { SAMPLE_RATE, type PcmBuffer } from "./types";

describe("PCM boundary rules", () => {
  it("rounds half frames forward consistently and measures duration", () => {
    expect(secondsToFrame(0.49 / SAMPLE_RATE)).toBe(0);
    expect(secondsToFrame(0.5 / SAMPLE_RATE)).toBe(1);
    expect(secondsToFrame(16)).toBe(705_600);
    expect(duration(allocatePcm(22_050))).toBe(0.5);
    expect(() => secondsToFrame(-1)).toThrow();
    expect(() => secondsToFrame(NaN)).toThrow();
  });

  it("rejects unsupported rates, channel layouts and nonfinite samples", () => {
    const invalid: PcmBuffer[] = [
      { sampleRate: 48_000, channels: [new Float32Array(1)] },
      { sampleRate: SAMPLE_RATE, channels: [] },
      { sampleRate: SAMPLE_RATE, channels: [new Float32Array(1), new Float32Array(2)] },
      { sampleRate: SAMPLE_RATE, channels: [new Float32Array([Infinity])] },
      { sampleRate: SAMPLE_RATE, channels: [new Float32Array([NaN])] },
    ];
    invalid.forEach((pcm) => expect(() => validatePcm(pcm)).toThrow());
    expect(() => validatePcm(allocatePcm(0, 2))).not.toThrow();
  });

  it("preflights duration and allocation before making arrays", () => {
    expect(allocationBytes(SAMPLE_RATE * 60, 2)).toBe(21_168_000);
    expect(() => allocatePcm(SAMPLE_RATE * 60 + 1)).toThrow(expect.objectContaining({ code: "range_too_long" }));
    expect(() => allocationBytes(-1, 1)).toThrow();
    expect(() => allocationBytes(1.5, 1)).toThrow();
    expect(() => allocationBytes(1, 3)).toThrow();
  });

  it("copies boundary data into independently owned arrays", () => {
    const input = { sampleRate: SAMPLE_RATE, channels: [new Float32Array([0.25, -0.5])] };
    const copy = copyPcm(input);
    copy.channels[0][0] = 1;
    expect([...input.channels[0]]).toEqual([0.25, -0.5]);
  });
});
