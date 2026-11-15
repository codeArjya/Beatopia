import type { TrackDetail } from "../types/api";
import { loadLocalFile, loadStem } from "./source-import";
import { sourceKey } from "./evaluate";
import { createEditorStore } from "../../stores/editor";
import { SAMPLE_RATE, type PcmBuffer } from "./types";
import { encodeWav } from "./wav";

function assert(condition: unknown, message: string): asserts condition { if (!condition) throw new Error(message); }

/** Actual browser decoder/resampling + source history; separate from UI/worker acceptance. */
export async function runSourceBrowserChecks(detail: TrackDetail, report: (line: string) => void): Promise<PcmBuffer> {
  const signal = new AbortController().signal;
  report(`Browser: ${navigator.userAgent}`);
  const stem = detail.stems.find((item) => item.stem === "drums");
  assert(stem, "Fixture drums required");
  const full = await loadStem(stem, detail, 5, 9, signal);
  const rangedUrl = URL.createObjectURL(new Blob([encodeWav(full.asset.pcm)], { type: "audio/wav" }));
  const store = createEditorStore();
  try {
    const loaded = await loadStem({ ...stem, url: rangedUrl, range_start_s: 5, range_end_s: 9 }, detail, 6, 8, signal);
    assert(loaded.asset.pcm.channels[0].length === 2 * SAMPLE_RATE, "Ranged duration");
    for (let i = 0; i < 2 * SAMPLE_RATE; i++) assert(Math.abs(loaded.asset.pcm.channels[0][i] - full.asset.pcm.channels[0][SAMPLE_RATE + i]) < 0.00005, "File-local crop samples");
    await store.getState().addSource(loaded.source, loaded.asset);
    await store.getState().apply([{ op: "slice", clip: "c1", count: 4, snap: "none" }, { op: "reverse", clip: "c1.4" }, { op: "arrange", order: ["c1.4", "c1.1", "c1.4"] }]);
    const edited = store.getState().current;
    assert(await store.getState().addSource(full.source, full.asset), "Add covering stem");
    store.getState().undo(); assert(store.getState().current === edited, "Undo must restore prior edit checkpoint");
    store.getState().redo(); assert(store.getState().current?.wire.clips.length === 2, "Redo stem source");
    report("PASS actual ranged WAV: track 6..8 maps to file 1..3; chop/reverse/repeated order + add/undo/redo preserve edits");
  } finally { URL.revokeObjectURL(rangedUrl); }

  // Build a genuine 48 kHz stereo WAV, independent of our 44.1 kHz-only exporter.
  const frames = 48000, bytes = new ArrayBuffer(44 + frames * 4), view = new DataView(bytes);
  for (const [at, text] of [[0, "RIFF"], [8, "WAVE"], [12, "fmt "], [36, "data"]] as const)
    for (let i = 0; i < text.length; i++) view.setUint8(at + i, text.charCodeAt(i));
  view.setUint32(4, bytes.byteLength - 8, true); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 2, true); view.setUint32(24, 48000, true); view.setUint32(28, 48000 * 4, true);
  view.setUint16(32, 4, true); view.setUint16(34, 16, true); view.setUint32(40, frames * 4, true);
  for (let i = 0; i < frames; i++) {
    view.setInt16(44 + i * 4, Math.round(12000 * Math.sin(2 * Math.PI * 440 * i / 48000)), true);
    view.setInt16(46 + i * 4, Math.round(8000 * Math.sin(2 * Math.PI * 660 * i / 48000)), true);
  }
  const file = new File([bytes], "48khz-stereo.wav", { type: "audio/wav" });
  // Exercise real browser failures too: the Node suite replaces decodeAudioData.
  const rejectFile = async (input: File, message: string) => {
    let failure: unknown;
    try { await loadLocalFile(input, signal); } catch (error) { failure = error; }
    assert(failure instanceof Error && failure.message.includes(message), `Expected ${message} for ${input.name}`);
  };
  await rejectFile(new File(["text"], "notes.txt"), "Choose a WAV");
  await rejectFile(new File([], "empty.wav"), "nonempty");
  await rejectFile(new File([new Uint8Array(25 * 1024 * 1024 + 1)], "oversized.wav"), "25 MB");
  await rejectFile(new File(["not audio"], "corrupt.wav"), "corrupt or unsupported");
  const longBytes = new ArrayBuffer(44 + 61 * frames * 4);
  new Uint8Array(longBytes).set(new Uint8Array(bytes, 0, 44));
  const longHeader = new DataView(longBytes);
  longHeader.setUint32(4, longBytes.byteLength - 8, true);
  longHeader.setUint32(40, longBytes.byteLength - 44, true);
  await rejectFile(new File([longBytes], "61-seconds.wav"), "60 seconds");
  const cancelled = new AbortController();
  const pending = loadLocalFile(file, cancelled.signal);
  cancelled.abort();
  let aborted = false;
  try { await pending; } catch (error) { aborted = error instanceof DOMException && error.name === "AbortError"; }
  assert(aborted, "Cancelled local file read must not publish audio");
  report("PASS browser local validation: unsupported/empty/over-25-MB/corrupt/61-second files rejected; cancelled read aborts");
  const first = await loadLocalFile(file, signal), second = await loadLocalFile(file, signal);
  // Chromium's decoder can round resampling down by one frame. Preserve its PCM
  // rather than padding audio to satisfy a theoretical duration.
  const localFrames = first.asset.pcm.channels[0].length;
  assert(first.asset.pcm.sampleRate === SAMPLE_RATE && Math.abs(localFrames - SAMPLE_RATE) <= 1 && first.asset.pcm.channels.length === 2, "48k -> 44.1k stereo resampling");
  assert(second.asset.pcm.channels[0].length === localFrames, "Repeated decode length");
  const monoBytes = new ArrayBuffer(44 + frames * 2);
  new Uint8Array(monoBytes).set(new Uint8Array(bytes, 0, 44));
  const monoHeader = new DataView(monoBytes);
  monoHeader.setUint32(4, monoBytes.byteLength - 8, true);
  monoHeader.setUint16(22, 1, true); monoHeader.setUint32(28, 48000 * 2, true);
  monoHeader.setUint16(32, 2, true); monoHeader.setUint32(40, frames * 2, true);
  for (let i = 0; i < frames; i++) monoHeader.setInt16(44 + i * 2, view.getInt16(44 + i * 4, true), true);
  const mono = await loadLocalFile(new File([monoBytes], "48khz-mono.wav"), signal);
  assert(mono.asset.pcm.sampleRate === SAMPLE_RATE && mono.asset.pcm.channels.length === 1 &&
    Math.abs(mono.asset.pcm.channels[0].length - SAMPLE_RATE) <= 1, "48k -> 44.1k mono resampling");
  assert(new DataView(encodeWav(mono.asset.pcm)).getUint16(22, true) === 1, "Mono WAV export");
  report(`PASS local 48k mono -> 44100 Hz (${mono.asset.pcm.channels[0].length} frames); mono WAV channel preserved`);
  assert(sourceKey(first.source) !== sourceKey(second.source), "Repeated file identities must differ");
  for (const source of [first.source, second.source]) {
    let revoked = false;
    try { await fetch(source.audio_url); } catch { revoked = true; }
    assert(revoked, "Import blob URL should already be revoked");
  }
  const local = createEditorStore();
  await local.getState().addSource(first.source, first.asset);
  await local.getState().apply([{ op: "trim", clip: "c1", start_s: 0.25, end_s: 0.75 }, { op: "reverse", clip: "c1" }]);
  const before = local.getState().current;
  await local.getState().addSource(second.source, second.asset);
  local.getState().undo(); assert(local.getState().current === before, "Local add undo must restore edits");
  local.getState().redo();
  const rendered = local.getState().current!.evaluation.rendered;
  const wav = encodeWav(rendered), header = new DataView(wav);
  assert(header.getUint32(24, true) === SAMPLE_RATE && header.getUint16(34, true) === 16 && header.getUint16(22, true) === 2, "WAV format");
  const decoded = await new OfflineAudioContext(2, 1, SAMPLE_RATE).decodeAudioData(wav);
  const expectedFrames = SAMPLE_RATE / 2 + localFrames;
  assert(decoded.length === expectedFrames && decoded.numberOfChannels === 2, "WAV browser roundtrip");
  report(`PASS local 48k stereo -> 44100 Hz (${localFrames} frames; one-frame resampling tolerance); unique sources, revoked import URLs, trim/reverse/add/undo/redo and stereo 16-bit WAV roundtrip (${expectedFrames} frames / ${expectedFrames / SAMPLE_RATE} s)`);
  report("UI drop/chooser, worker queue and musical listening remain separate checks.");
  return rendered;
}
