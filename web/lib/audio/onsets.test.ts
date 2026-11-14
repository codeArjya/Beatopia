import { expect, it } from "vitest";
import { detectOnsets } from "./onsets";
import { resolveCuts, slice } from "./slice";
import { SAMPLE_RATE } from "./types";
import { readFileSync } from "node:fs";

it("finds repeatable interior impulse cuts without stereo cancellation or input mutation", () => {
  const samples = new Float32Array(SAMPLE_RATE * 2);
  for (const time of [0.5, 1, 1.5]) samples[Math.round(time * SAMPLE_RATE)] = 1;
  const opposite = samples.map((sample) => -sample);
  const pcm = { sampleRate: SAMPLE_RATE, channels: [samples, opposite] };
  expect(detectOnsets(pcm)).toEqual([0.5, 1, 1.5]);
  expect(resolveCuts(pcm, { count: 4, snap: "transient" })).toEqual([22050, 44100, 66150]);
  expect(slice(pcm, { count: 4, snap: "transient" }).reduce((sum, part) => sum + part.channels[0].length, 0)).toBe(samples.length);
  expect(samples[22050]).toBe(1); expect(opposite[22050]).toBe(-1);
});

it("rejects silent transient snaps and collapsed cuts; ignores low steady noise", () => {
  const silent = { sampleRate: SAMPLE_RATE, channels: [new Float32Array(SAMPLE_RATE)] };
  expect(detectOnsets(silent)).toEqual([]);
  expect(() => resolveCuts(silent, { count: 4, snap: "transient" })).toThrow("No interior transients");
  const noisy = { ...silent, channels: [Float32Array.from({ length: SAMPLE_RATE }, (_, i) => Math.sin(i * 123.456) * 0.0001)] };
  expect(detectOnsets(noisy)).toEqual([]);
  silent.channels[0][SAMPLE_RATE / 2] = 1;
  expect(() => resolveCuts(silent, { count: 4, snap: "transient" })).toThrow("unique");
});

it("produces deterministic, sorted interior cuts on the actual fixture drums", () => {
  const file = readFileSync("public/fixtures/audio/drums.wav");
  const count = file.readUInt16LE(22), frames = file.readUInt32LE(40) / (2 * count);
  const pcm = { sampleRate: SAMPLE_RATE, channels: Array.from({ length: count }, (_, channel) =>
    Float32Array.from({ length: frames }, (_, frame) => file.readInt16LE(44 + (frame * count + channel) * 2) / 32768)) };
  const first = detectOnsets(pcm);
  expect(first.length).toBeGreaterThan(8);
  expect(detectOnsets(pcm)).toEqual(first);
  expect(first.every((value, i) => value > (first[i - 1] ?? 0) && value < frames / SAMPLE_RATE)).toBe(true);
  const cuts = resolveCuts(pcm, { count: 4, snap: "transient" });
  expect(cuts).toHaveLength(3);
  expect(resolveCuts(pcm, { count: 4, snap: "transient" })).toEqual(cuts);
});
