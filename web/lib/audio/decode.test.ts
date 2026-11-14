import { expect, it } from "vitest";
import { fromAudioBuffer, toAudioBuffer } from "./decode";
import { SAMPLE_RATE } from "./types";

it("copies clip-relative frames at the browser boundary and rejects unsupported ranges", () => {
  const channel = Float32Array.from([0, 1, 2, 3]);
  const buffer = { sampleRate: SAMPLE_RATE, duration: 4 / SAMPLE_RATE, numberOfChannels: 1,
    getChannelData: () => channel } as unknown as AudioBuffer;
  const pcm = fromAudioBuffer(buffer, 1 / SAMPLE_RATE, 3 / SAMPLE_RATE);
  expect(Array.from(pcm.channels[0])).toEqual([1, 2]);
  pcm.channels[0][0] = 8;
  expect(channel[1]).toBe(1);
  expect(() => fromAudioBuffer(buffer, 0, 1)).toThrow("cover");
  expect(() => fromAudioBuffer({ ...buffer, sampleRate: 48000 } as AudioBuffer)).toThrow("44100");
});

it("copies each channel to a fresh Web Audio buffer", () => {
  const stored: Float32Array[] = [];
  const output = { copyToChannel: (channel: Float32Array, index: number) => { stored[index] = channel; } };
  const context = { createBuffer: (channels: number, frames: number, rate: number) => {
    expect([channels, frames, rate]).toEqual([2, 2, SAMPLE_RATE]); return output;
  } } as unknown as BaseAudioContext;
  const source = Float32Array.from([0.1, 0.2]);
  expect(toAudioBuffer(context, { sampleRate: SAMPLE_RATE, channels: [source, source] })).toBe(output);
  expect(stored[0]).not.toBe(source);
  expect(stored[0]).not.toBe(stored[1]);
});
