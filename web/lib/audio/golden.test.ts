import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, it } from "vitest";
import fixture from "../../../shared/fixtures/track_detail.json";
import { createEditorStore } from "../../stores/editor";
import { sourceKey } from "./evaluate";
import { SAMPLE_RATE } from "./types";
import { encodeWav, exportFilename } from "./wav";

it("exports the real jam_1532881 fixture after four chops, reverse, undo and redo", async () => {
  const input = readFileSync(resolve("public/fixtures/audio/mix.wav"));
  const channels = input.readUInt16LE(22);
  const frames = input.readUInt32LE(40) / (channels * 2);
  expect(input.toString("ascii", 0, 4)).toBe("RIFF");
  expect(input.toString("ascii", 36, 40)).toBe("data");
  expect(input.readUInt32LE(24)).toBe(SAMPLE_RATE);
  expect(input.readUInt16LE(34)).toBe(16);
  expect(frames).toBe(705600);
  expect(channels).toBe(2);
  const pcm = { sampleRate: SAMPLE_RATE, channels: Array.from({ length: channels }, (_, channel) =>
    Float32Array.from({ length: frames }, (_, frame) => input.readInt16LE(44 + (frame * channels + channel) * 2) / 32768)) };
  const source = { track_id: fixture.track.id, audio_url: fixture.audio_url, start_s: 0, end_s: 16 };
  const store = createEditorStore();
  await store.getState().initialize({ clips: [{ id: "c1", source }], ops: [], arrangement: [], bpm: 90 },
    new Map([[sourceKey(source), { pcm, origin: 0, beatTimes: fixture.beat_times, bpm: 90 }]]));
  await store.getState().apply([{ op: "slice", clip: "c1", count: 4, snap: "none" }]);
  const chopped = store.getState().current;
  await store.getState().apply([{ op: "reverse", clip: "c1.4" }]);
  const reversed = store.getState().current;
  store.getState().undo();
  expect(store.getState().current).toBe(chopped);
  store.getState().redo();
  expect(store.getState().current).toBe(reversed);
  expect(store.getState().current!.evaluation.order).toEqual(["c1.1", "c1.2", "c1.3", "c1.4"]);
  const output = encodeWav(store.getState().current!.evaluation.rendered);
  const header = new DataView(output);
  expect(output.byteLength).toBe(2822444);
  expect(header.getUint32(24, true)).toBe(44100);
  expect(header.getUint16(34, true)).toBe(16);
  expect(header.getUint16(22, true)).toBe(2);
  expect(header.getUint32(40, true) / header.getUint16(32, true)).toBe(705600);
  let mismatches = 0;
  const lastStart = frames * 3 / 4;
  for (let frame = 0; frame < frames; frame++) {
    const sourceFrame = frame < lastStart ? frame : frames - 1 - (frame - lastStart);
    for (let channel = 0; channel < channels; channel++) {
      const sample = pcm.channels[channel][sourceFrame];
      const expected = Math.round(sample * (sample < 0 ? 32768 : 32767));
      if (header.getInt16(44 + (frame * channels + channel) * 2, true) !== expected) mismatches++;
    }
  }
  expect(mismatches).toBe(0);
  // Opt-in artifact for independent file-reader inspection; ordinary tests only read the fixture.
  if (process.env.WS4_GOLDEN_WAV) writeFileSync(process.env.WS4_GOLDEN_WAV, new Uint8Array(output));
});

it("sanitizes download metadata and names unknown source metadata honestly", () => {
  expect(exportFilename({ title: 'Late: Bloom/Instrumental?', bpm: 90, key: 'A minor' })).toBe("Late- Bloom-Instrumental--90bpm-A minor.wav");
  expect(exportFilename({ title: "Track" })).toBe("Track-unknownbpm-unknown.wav");
});
