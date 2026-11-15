/** Development acceptance checks against live public storage, with snapshot metadata.
 * This deliberately does not claim to exercise WS2's production TrackDetail endpoint.
 */
import type { Op, TrackDetail } from "../types/api";
import { loadSource } from "./decode";
import { resolveEntry } from "./entry";
import { sourceKey } from "./evaluate";
import { renderOffline } from "./native-offline";
import { SAMPLE_RATE, type PcmBuffer } from "./types";
import { encodeWav } from "./wav";
import { createEditorStore } from "../../stores/editor";

function assert(condition: boolean, message: string): asserts condition {
  if (!condition) throw new Error(message);
}
async function rejects(run: () => Promise<unknown>, message: string) {
  try { await run(); } catch (error) {
    assert(error instanceof Error && error.message.includes(message), `Unexpected error: ${String(error)}`);
    return;
  }
  throw new Error(`Expected rejection containing: ${message}`);
}

export async function runHeroChecks(detail: TrackDetail, report: (line: string) => void): Promise<PcmBuffer> {
  report(`Browser: ${navigator.userAgent}`);
  report(`Live public storage: ${detail.track.id} · ${detail.track.title} · ${detail.track.license}`);
  report("Metadata is a read-only database snapshot. Production API and editor UI acceptance remain separate.");
  assert(detail.track.is_hero === true, "Expected a real hero track");
  const entry = { trackId: detail.track.id, start: 5, end: 15, stem: "mix" as const };
  const resolved = resolveEntry(entry, detail);
  const signal = new AbortController().signal;
  const pcm = await loadSource(resolved.source, resolved.origin, signal);
  assert(pcm.channels[0].length === 10 * SAMPLE_RATE && pcm.channels.some((channel) => channel.some((sample) => sample !== 0)), "Mix decode/window failed");
  report(`PASS live mix CORS/decode: track 5..15 s, ${pcm.channels.length} channels, ${pcm.channels[0].length} frames`);

  const drums = resolveEntry({ ...entry, stem: "drums" }, detail);
  const stemPcm = await loadSource(drums.source, drums.origin, signal);
  assert(stemPcm.channels[0].length === 10 * SAMPLE_RATE, "Stem window failed");
  report(`PASS live drums CORS/decode: file origin ${drums.origin} s, track 5..15 s`);
  // Exercise a ranged file using an actual decoded hero stem; no ranged remote object is assumed.
  const rangedUrl = URL.createObjectURL(new Blob([encodeWav(stemPcm)], { type: "audio/wav" }));
  try {
    const ranged = await loadSource({ ...drums.source, audio_url: rangedUrl, start_s: 6, end_s: 9 }, 5, signal);
    assert(ranged.channels[0].length === 3 * SAMPLE_RATE, "Ranged stem file-local duration failed");
    for (let i = 0; i < ranged.channels[0].length; i++) {
      assert(Math.abs(ranged.channels[0][i] - stemPcm.channels[0][SAMPLE_RATE + i]) < 0.00005, "Ranged stem file-local samples failed");
    }
    report("PASS ranged-file adapter: hero drums wrapped as 5..15 s WAV; track 6..9 maps to file 1..4 s");
  } finally { URL.revokeObjectURL(rangedUrl); }

  const store = createEditorStore(renderOffline);
  await store.getState().initialize({ clips: [{ id: "c1", source: resolved.source }], ops: [], bpm: detail.track.bpm },
    new Map([[sourceKey(resolved.source), { pcm, origin: 5, beatTimes: detail.beat_times, bpm: detail.track.bpm ?? null }]]));
  assert(!!store.getState().current, store.getState().error ?? "Initialize failed");
  const apply = async (ops: Op[]) => { await store.getState().apply(ops); assert(!store.getState().error, store.getState().error ?? "Edit failed"); };
  await apply([{ op: "trim", clip: "c1", start_s: 1, end_s: 9 }]);
  await apply([{ op: "slice", clip: "c1", count: 4, snap: "none" }]);
  await apply([{ op: "reverse", clip: "c1.4" }]);
  await apply([{ op: "repitch", clip: "c1.4", semitones: -3 }]);
  const repitchedFrames = Math.round(2 * SAMPLE_RATE / 2 ** (-3 / 12));
  assert(store.getState().current!.evaluation.clips.get("c1.4")!.pcm.channels[0].length === repitchedFrames, "Real hero -3 duration failed");
  const beforeArrange = store.getState().current;
  const order = ["c1.4", "c1.1", "c1.4", "c1.3", "c1.2"];
  await apply([{ op: "arrange", order }]);
  const arranged = store.getState().current;
  store.getState().undo(); assert(store.getState().current === beforeArrange, "Real hero undo failed");
  store.getState().redo(); assert(store.getState().current === arranged, "Real hero redo failed");
  const golden = arranged!.evaluation.rendered;
  const frames = repitchedFrames * 2 + 6 * SAMPLE_RATE;
  assert(golden.channels[0].length === frames, "Real hero arrangement frames failed");
  report(`PASS hero replay: trim 1..9, four chops, reverse c1.4, -3 repitch (${repitchedFrames} frames), reorder/duplicate, undo/redo`);
  await store.getState().apply([{ op: "arrange", order: Array.from({ length: 6 }, () => order).flat() }]);
  assert(store.getState().error?.includes("60 seconds") === true && store.getState().current === arranged, "Output cap must retain previous audio/history");
  report("PASS >60-second output rejected without changing the current arrangement");
  await rejects(() => renderOffline(pcm, { op: "stretch_to_bpm", clip: "c1", target_bpm: 120 }, null), "BPM");
  await rejects(() => loadSource({ ...resolved.source, start_s: 0, end_s: 61 }, 0, signal), "60 seconds");
  await rejects(() => loadSource({ ...resolved.source, audio_url: "/fixtures/audio/ws4-missing-check.wav" }, 0, signal), "HTTP 404");
  const corruptUrl = URL.createObjectURL(new Blob(["not audio"], { type: "audio/wav" }));
  try {
    await rejects(() => loadSource({ ...resolved.source, audio_url: corruptUrl }, 0, signal), "could not be decoded");
  } finally { URL.revokeObjectURL(corruptUrl); }
  const retryUrl = URL.createObjectURL(new Blob([encodeWav(pcm)], { type: "audio/wav" }));
  try {
    const retry = await loadSource({ ...resolved.source, audio_url: retryUrl }, 5, signal);
    assert(retry.channels[0].length === pcm.channels[0].length, "Decode retry failed");
  } finally { URL.revokeObjectURL(retryUrl); }
  report("PASS missing-BPM fit rejection, input cap, HTTP 404, corrupt-file decode error and successful valid decode afterward");
  const wav = encodeWav(golden), header = new DataView(wav), wavBytes = wav.byteLength;
  assert(header.getUint32(24, true) === SAMPLE_RATE && header.getUint16(34, true) === 16, "Hero WAV format failed");
  const decoded = await new OfflineAudioContext(2, 1, SAMPLE_RATE).decodeAudioData(wav);
  assert(decoded.length === frames && decoded.numberOfChannels === golden.channels.length, "Hero WAV browser roundtrip failed");
  // decodeAudioData transfers/detaches its input; retain the size before decoding.
  report(`PASS hero WAV encode/decode: 44100 Hz, 16-bit PCM, ${golden.channels.length} channels, ${frames} frames, ${(frames / SAMPLE_RATE).toFixed(6)} s, ${wavBytes} bytes`);
  return golden;
}
