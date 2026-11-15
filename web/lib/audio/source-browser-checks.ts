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
  const first = await loadLocalFile(file, signal), second = await loadLocalFile(file, signal);
  assert(first.asset.pcm.sampleRate === SAMPLE_RATE && first.asset.pcm.channels[0].length === SAMPLE_RATE && first.asset.pcm.channels.length === 2, "48k -> 44.1k stereo resampling");
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
  assert(decoded.length === 66150 && decoded.numberOfChannels === 2, "WAV browser roundtrip");
  report("PASS local 48k stereo -> 44100 Hz; unique sources, revoked import URLs, trim/reverse/add/undo/redo and stereo 16-bit WAV roundtrip (66150 frames / 1.5 s)");
  report("UI drop/chooser, worker queue and musical listening remain separate checks.");
  return rendered;
}
