import { afterEach, expect, it, vi } from "vitest";
import { fromAudioBuffer, loadSource, toAudioBuffer } from "./decode";
import { evaluate, sourceKey } from "./evaluate";
import { SAMPLE_RATE } from "./types";

afterEach(() => vi.unstubAllGlobals());

it("copies clip-relative frames at the browser boundary and rejects unsupported ranges", () => {
  const channel = Float32Array.from([0, 1, 2, 3]);
  const buffer = { sampleRate: SAMPLE_RATE, length: 4, duration: 4 / SAMPLE_RATE, numberOfChannels: 1,
    getChannelData: () => channel } as unknown as AudioBuffer;
  const pcm = fromAudioBuffer(buffer, 1 / SAMPLE_RATE, 3 / SAMPLE_RATE);
  expect(Array.from(pcm.channels[0])).toEqual([1, 2]);
  pcm.channels[0][0] = 8;
  expect(channel[1]).toBe(1);
  expect(() => fromAudioBuffer(buffer, 0, 1)).toThrow("cover");
  expect(() => fromAudioBuffer({ ...buffer, sampleRate: 48000 } as AudioBuffer)).toThrow("44100");
});

it("loads a ranged stem using file-local offset and replays absolute wire times, including subframe starts", async () => {
  const data = Float32Array.from([0, 1, 2, 3, 4, 5, 6, 7]);
  const decoded = { sampleRate: SAMPLE_RATE, length: 8, duration: 8 / SAMPLE_RATE, numberOfChannels: 1, getChannelData: () => data };
  const decode = vi.fn(async () => decoded);
  vi.stubGlobal("OfflineAudioContext", vi.fn(function () { return { decodeAudioData: decode }; }));
  const download = vi.fn(async () => new Response(new Uint8Array([1, 2, 3])));
  vi.stubGlobal("fetch", download);
  const source = { track_id: "hero", stem: "drums" as const, audio_url: "https://audio.example/stems/range.mp3", start_s: 5 + 1.6 / SAMPLE_RATE, end_s: 5 + 5.2 / SAMPLE_RATE };
  const signal = new AbortController().signal;
  const pcm = await loadSource(source, 5, signal);
  expect(Array.from(pcm.channels[0])).toEqual([2, 3, 4, 5]);
  expect(download).toHaveBeenCalledWith(source.audio_url, { signal, mode: "cors", credentials: "omit" });
  const result = await evaluate(new Map([[sourceKey(source), { pcm, origin: source.start_s, bpm: null, beatTimes: [] }]]), { clips: [{ id: "c1", source }], ops: [] });
  expect(result.rendered.channels[0]).toHaveLength(4);
});

it("reports network/CORS, HTTP and decode failures distinctly; preserves abort and preflights the window cap", async () => {
  const source = { track_id: "t", audio_url: "https://audio.example/mix.mp3", start_s: 0, end_s: 1 };
  const signal = new AbortController().signal;
  const download = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
  vi.stubGlobal("fetch", download);
  await expect(loadSource(source, 0, signal)).rejects.toThrow("CORS");
  download.mockResolvedValue(new Response(null, { status: 403 }));
  await expect(loadSource(source, 0, signal)).rejects.toThrow("HTTP 403");
  download.mockResolvedValue(new Response(new Uint8Array([1])));
  vi.stubGlobal("OfflineAudioContext", vi.fn(function () { return { decodeAudioData: async () => { throw new Error("decode"); } }; }));
  await expect(loadSource(source, 0, signal)).rejects.toThrow("corrupt or unsupported");
  const aborted = new AbortController(); aborted.abort();
  download.mockRejectedValue(new TypeError("fetch"));
  await expect(loadSource(source, 0, aborted.signal)).rejects.toMatchObject({ name: "AbortError" });
  download.mockClear();
  await expect(loadSource({ ...source, end_s: 61 }, 0, signal)).rejects.toMatchObject({ code: "range_too_long" });
  expect(download).not.toHaveBeenCalled();
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
