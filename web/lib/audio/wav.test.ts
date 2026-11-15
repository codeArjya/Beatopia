import { describe, expect, it } from "vitest";
import { gain, loop, reverse } from "./ops";
import { allocatePcm } from "./pcm";
import { concatenate } from "./render";
import { slice } from "./slice";
import { SAMPLE_RATE } from "./types";
import { encodeWav } from "./wav";

describe("arrangement concatenation", () => {
  it("duplicates mono channels for stereo and preserves repeated occurrences", () => {
    const mono = { sampleRate: SAMPLE_RATE, channels: [new Float32Array([0.25, 0.5])] };
    const stereo = { sampleRate: SAMPLE_RATE, channels: [new Float32Array([1]), new Float32Array([-1])] };
    const result = concatenate([mono, stereo, mono]);
    expect([...result.channels[0]]).toEqual([0.25, 0.5, 1, 0.25, 0.5]);
    expect([...result.channels[1]]).toEqual([0.25, 0.5, -1, 0.25, 0.5]);
    result.channels[0][0] = 7;
    expect(mono.channels[0][0]).toBe(0.25);
    expect(concatenate([mono], 2).channels).toHaveLength(2);
    expect(concatenate([], 2)).toEqual(allocatePcm(0, 2));
  });

  it("preflights the complete arrangement, including repeats", () => {
    const input = allocatePcm(31 * SAMPLE_RATE);
    expect(() => concatenate([input, input])).toThrow(expect.objectContaining({ code: "range_too_long" }));
  });
});

describe("WAV encoding", () => {
  it("writes RIFF/fmt/data chunks with exact stereo byte counts and interleaving", () => {
    const input = {
      sampleRate: SAMPLE_RATE,
      channels: [new Float32Array([-2, -0.5, 0, 0.5, 2]), new Float32Array([1, 0.5, 0, -0.5, -1])],
    };
    const buffer = encodeWav(input);
    const view = new DataView(buffer);
    const ascii = (offset: number, size: number) => new TextDecoder().decode(new Uint8Array(buffer, offset, size));
    expect(buffer.byteLength).toBe(64);
    expect(ascii(0, 4)).toBe("RIFF");
    expect(view.getUint32(4, true)).toBe(56);
    expect(ascii(8, 8)).toBe("WAVEfmt ");
    expect(view.getUint32(16, true)).toBe(16);
    expect(view.getUint16(20, true)).toBe(1);
    expect(view.getUint16(22, true)).toBe(2);
    expect(view.getUint32(24, true)).toBe(44_100);
    expect(view.getUint32(28, true)).toBe(176_400);
    expect(view.getUint16(32, true)).toBe(4);
    expect(view.getUint16(34, true)).toBe(16);
    expect(ascii(36, 4)).toBe("data");
    expect(view.getUint32(40, true)).toBe(20);
    expect(Array.from({ length: 10 }, (_, i) => view.getInt16(44 + i * 2, true)))
      .toEqual([-32768, 32767, -16384, 16384, 0, 0, 16384, -16384, 32767, -32768]);
    expect([...input.channels[0]]).toEqual([-2, -0.5, 0, 0.5, 2]);
  });

  it("writes mono and empty audio without adding padding or samples", () => {
    const mono = new DataView(encodeWav(allocatePcm(3)));
    expect(mono.byteLength).toBe(50);
    expect(mono.getUint16(22, true)).toBe(1);
    expect(mono.getUint32(28, true)).toBe(88_200);
    expect(mono.getUint16(32, true)).toBe(2);
    expect(mono.getUint32(40, true)).toBe(6);
    expect(encodeWav(allocatePcm(0)).byteLength).toBe(44);
  });

  it("exports a chop/reverse/repeat sequence with sample-exact ordering", () => {
    const source = { sampleRate: SAMPLE_RATE, channels: [new Float32Array([0, 0.25, 0.5, 0.75, 1, -0.25, -0.5, -1])] };
    const children = slice(source, { count: 4, snap: "none" });
    const result = concatenate([children[2], reverse(children[0]), loop(children[3], 2)]);
    const view = new DataView(encodeWav(gain(result, 0)));
    expect(view.getUint32(40, true)).toBe(16);
    expect(Array.from({ length: 8 }, (_, i) => view.getInt16(44 + i * 2, true)))
      .toEqual([32767, -8192, 8192, 0, -16384, -32768, -16384, -32768]);
  });
});
