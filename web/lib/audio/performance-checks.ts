import type { EditorState, Op } from "../types/api";
import { evaluate, sourceKey, type Evaluation, type SourceRegistry } from "./evaluate";
import { SAMPLE_RATE } from "./types";
import { PrefixCache } from "./cache";

/** Deterministic stereo 16 bars in 4/4 at 120 BPM: 32 seconds. */
export function performanceFixture(): { registry: SourceRegistry; state: EditorState } {
  const source = { track_id: "profile", audio_url: "profile.wav", start_s: 0, end_s: 32 };
  const channel = Float32Array.from({ length: 32 * SAMPLE_RATE }, (_, i) => 0.2 * Math.sin(i * 2 * Math.PI * 220 / SAMPLE_RATE));
  return { registry: new Map([[sourceKey(source), { pcm: { sampleRate: SAMPLE_RATE, channels: [channel, channel.slice()] },
    origin: 0, bpm: 120, beatTimes: Array.from({ length: 64 }, (_, i) => i / 2) }]]),
  state: { bpm: 120, clips: [{ id: "c1", source }], arrangement: [], ops: [
    { op: "gain", clip: "c1", db: -3 }, { op: "fade_in", clip: "c1", ms: 20 },
    { op: "fade_out", clip: "c1", ms: 20 }, { op: "reverse", clip: "c1" },
    { op: "slice", clip: "c1", count: 4, snap: "none" },
    { op: "arrange", order: ["c1.4", "c1.1", "c1.3", "c1.2"] },
  ] } };
}

export async function profileReplay(
  replay: (state: EditorState) => Promise<Evaluation>, state: EditorState,
  beforeEach?: () => Promise<unknown>,
  clip = "c1",
): Promise<Record<string, number>> {
  const timings: Record<string, number> = {};
  for (const op of [{ op: "reverse", clip }, { op: "gain", clip, db: -1 },
    { op: "normalize", clip, peak_db: -1 }] satisfies Op[]) {
    const runs: number[] = [];
    for (let i = 0; i < 5; i++) {
      await beforeEach?.();
      const start = performance.now();
      await replay({ ...state, ops: [...state.ops, op] });
      runs.push(performance.now() - start);
    }
    timings[`${op.op} median ms`] = Number(runs.sort((a, b) => a - b)[2].toFixed(2));
    timings[`${op.op} max ms`] = Number(Math.max(...runs).toFixed(2));
  }
  return timings;
}

export const freshReplay = (registry: SourceRegistry) => (state: EditorState) => evaluate(registry, state);

/** Used by the development harness and Node profile; each measured suffix is uncached. */
export async function runPerformanceChecks(report: (line: string) => void) {
  const { registry, state } = performanceFixture();
  const root = { ...state, ops: state.ops.slice(0, 4) };
  const cache = new PrefixCache();
  const signal = new AbortController().signal;
  // Include the same initial paint opportunity used by store apply/preview.
  const replay = (wire: EditorState) => evaluate(registry, wire, undefined, { cache, signal });
  const fresh = await profileReplay((wire) => evaluate(registry, wire, undefined, { signal }), root);
  const cached = await profileReplay(replay, root, async () => { cache.clear(); await replay(root); });
  report(`16 bars, 4/4, 120 BPM, 32 s, stereo/44100 Hz; 5 runs, uncached appended op. Fresh: ${JSON.stringify(fresh)}`);
  report(`Cached prefix: ${JSON.stringify(cached)}; target <150 ms: ${Object.values(cached).every((ms) => ms < 150) ? "PASS (including max)" : "MISSED (see timings)"}`);
  const before = await replay(state);
  const next = { ...state, ops: [...state.ops, { op: "reverse", clip: "c1.4" } as const] };
  const result = await replay(next);
  const expected = await freshReplay(registry)(next);
  if (before.clips.get("c1.1") !== result.clips.get("c1.1")) throw new Error("Unaffected buffer was not reused.");
  for (let c = 0; c < expected.rendered.channels.length; c++) {
    if (!expected.rendered.channels[c].every((value, i) => value === result.rendered.channels[c][i])) throw new Error("Cached/fresh samples differ.");
  }
  report(`PASS cached/fresh samples and unaffected PCM reuse; retained ${JSON.stringify(cache.stats)} (64 MiB / 12 entries).`);
  cache.clear();
  if (cache.stats.bytes !== 0) throw new Error("Cache clear retained resources.");
  report("PASS cache clear releases all retained entries.");
  return { fresh, cached };
}
