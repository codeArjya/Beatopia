import { afterEach, expect, it, vi } from "vitest";
import type { Stem, TrackDetail } from "../types/api";
import { coveringStems, loadLocalFile, loadStem, MAX_LOCAL_BYTES } from "./source-import";
import { SAMPLE_RATE } from "./types";
import { sourceKey } from "./evaluate";
import { createEditorStore } from "../../stores/editor";
import { encodeWav } from "./wav";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const stem: Stem = { track_id: "hero", stem: "drums", url: "range.wav", range_start_s: 5, range_end_s: 9, model: "htdemucs" };
const detail: TrackDetail = { track: { id: "hero", title: "Hero", source: "jamendo", license: "CC0", attribution: "Artist", duration_s: 20, bpm: 90 }, audio_url: "mix.wav", beat_times: [6, 7, 8], windows: [], stems: [stem] };

function decoder(frames = 8, channels = 1, decode?: () => Promise<AudioBuffer>) {
  const decoded = { sampleRate: SAMPLE_RATE, length: frames, duration: frames / SAMPLE_RATE, numberOfChannels: channels,
    getChannelData: () => Float32Array.from({ length: frames }, (_, i) => i / 8) } as unknown as AudioBuffer;
  const constructor = vi.fn(function () { return { decodeAudioData: decode ?? vi.fn(async () => decoded) }; });
  vi.stubGlobal("OfflineAudioContext", constructor);
  return constructor;
}
function urls() {
  let id = 0;
  const create = vi.spyOn(URL, "createObjectURL").mockImplementation(() => `blob:local-${++id}`);
  const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  return { create, revoke };
}
const file = () => new File([new Uint8Array([1, 2, 3])], "beat.wav", { type: "audio/wav" });

it("selects the smallest covering same-track stem and crops file-local frames while retaining absolute wire times", async () => {
  expect(coveringStems([{ ...stem, range_start_s: 0, range_end_s: 20 }, stem, { ...stem, track_id: "other" }, { ...stem, range_end_s: 6 }], "hero", 6, 8)).toEqual([stem]);
  decoder();
  vi.stubGlobal("fetch", vi.fn(async () => new Response(new Uint8Array([1]))));
  const start = 5 + 2 / SAMPLE_RATE, end = 5 + 6 / SAMPLE_RATE;
  const loaded = await loadStem(stem, detail, start, end, new AbortController().signal);
  expect(loaded.source).toMatchObject({ start_s: start, end_s: end, track_id: "hero" });
  expect(loaded.asset.origin).toBe(start);
  expect(Array.from(loaded.asset.pcm.channels[0])).toEqual([0.25, 0.375, 0.5, 0.625]);
  expect(loaded.asset.metadata?.license).toBe("CC0");
  await expect(loadStem({ ...stem, track_id: "other" }, detail, start, end, new AbortController().signal)).rejects.toThrow("cover");
});

it("imports unique local sources at 44100, edits/exports without fetch, and immediately revokes their URLs", async () => {
  const { create, revoke } = urls();
  const constructor = decoder();
  const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
  const signal = new AbortController().signal;
  const first = await loadLocalFile(file(), signal), second = await loadLocalFile(file(), signal);
  expect(constructor).toHaveBeenCalledWith(2, 1, SAMPLE_RATE);
  expect(first.source.track_id).toBe("local");
  expect(sourceKey(first.source)).not.toBe(sourceKey(second.source));
  expect(first.asset).toMatchObject({ bpm: null, beatTimes: [], metadata: { license: "Local file — license not supplied" } });
  expect(create).toHaveBeenCalledTimes(2); expect(revoke.mock.calls).toEqual([["blob:local-1"], ["blob:local-2"]]);
  const store = createEditorStore();
  await store.getState().addSource(first.source, first.asset);
  await store.getState().apply([{ op: "reverse", clip: "c1" }]);
  const before = store.getState().current;
  await store.getState().addSource(second.source, second.asset);
  expect(store.getState().current!.wire.clips).toHaveLength(2);
  store.getState().undo(); expect(store.getState().current).toBe(before);
  store.getState().redo();
  const wav = new DataView(encodeWav(store.getState().current!.evaluation.rendered));
  expect(wav.getUint32(24, true)).toBe(44100); expect(wav.getUint16(34, true)).toBe(16);
  expect(wav.getUint32(40, true)).toBe(16 * 2);
  expect(fetch).not.toHaveBeenCalled();
});

it("rejects oversized/unsupported files before URL/decode, and revokes on corruption, abort and long/multichannel rejection", async () => {
  const { create, revoke } = urls(); const constructor = decoder();
  const signal = new AbortController().signal;
  await expect(loadLocalFile(new File(["text"], "text.txt"), signal)).rejects.toThrow("Choose a WAV");
  await expect(loadLocalFile({ name: "huge.wav", size: MAX_LOCAL_BYTES + 1 } as File, signal)).rejects.toThrow("25 MB");
  expect(create).not.toHaveBeenCalled(); expect(constructor).not.toHaveBeenCalled();
  decoder(8, 1, async () => { throw new Error("decode"); });
  await expect(loadLocalFile(file(), signal)).rejects.toThrow("corrupt");
  decoder(61 * SAMPLE_RATE);
  await expect(loadLocalFile(file(), signal)).rejects.toThrow("60 seconds");
  decoder(8, 3);
  await expect(loadLocalFile(file(), signal)).rejects.toThrow("one or two");
  const controller = new AbortController();
  const pendingFile = file();
  vi.spyOn(pendingFile, "arrayBuffer").mockImplementation(async () => { controller.abort(); return new ArrayBuffer(1); });
  await expect(loadLocalFile(pendingFile, controller.signal)).rejects.toMatchObject({ name: "AbortError" });
  expect(revoke).toHaveBeenCalledTimes(4);
});
