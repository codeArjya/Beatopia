import type { ClipSource, EditorState, Op } from "../types/api";
import * as ops from "./ops";
import { allocationBytes, duration, secondsToFrame, validatePcm } from "./pcm";
import { concatenate } from "./render";
import { mapBeatTimes, resolveCuts } from "./slice";
import { AudioEngineError, SAMPLE_RATE, type PcmBuffer } from "./types";
import { planOfflineFrames } from "./offline";

export interface SourceAsset {
  readonly pcm: PcmBuffer;
  /** Absolute track time of the first decoded frame. */
  readonly origin: number;
  readonly beatTimes: readonly number[];
  readonly bpm: number | null;
  /** Display-only provenance; never serialized into EditorState. */
  readonly metadata?: { title: string; license: string; attribution: string; key?: string | null };
}
export type SourceRegistry = ReadonlyMap<string, SourceAsset>;
export const sourceKey = (source: ClipSource): string => JSON.stringify([
  source.track_id, source.stem ?? "mix", source.audio_url, source.start_s, source.end_s,
]);

export interface EvaluatedClip {
  readonly pcm: PcmBuffer;
  readonly beatTimes: readonly number[];
  readonly bpm: number | null;
  /** Display tempo follows rate changes; bpm remains the original fit reference. */
  readonly tempoBpm: number | null;
}
export interface Evaluation {
  readonly clips: ReadonlyMap<string, EvaluatedClip>;
  readonly leaves: readonly string[];
  readonly order: readonly string[];
  readonly sliced: ReadonlySet<string>;
  readonly rendered: PcmBuffer;
}
type OfflineOp = Extract<Op, { op: "repitch" | "pitch_shift" | "stretch_to_bpm" | "filter" }>;
/** Later browser DSP can be injected without importing browser APIs into replay. */
export type OfflineRenderer = (pcm: PcmBuffer, op: OfflineOp, bpm: number | null) => Promise<PcmBuffer>;

const fail = (message: string): never => { throw new AudioEngineError("bad_request", message); };

export async function evaluate(
  registry: SourceRegistry, state: EditorState, offline?: OfflineRenderer,
): Promise<Evaluation> {
  const clips = new Map<string, EvaluatedClip>();
  const sliced = new Set<string>();
  let leaves: string[] = [];
  let order = [...(state.arrangement ?? [])];
  let minimumChannels: 1 | 2 = 1;
  for (const root of state.clips) {
    if (!root.id || clips.has(root.id)) fail("Root clip IDs must be unique and nonempty.");
    const asset = registry.get(sourceKey(root.source));
    if (!asset) fail(`Source for ${root.id} is not loaded.`);
    const { pcm, origin, beatTimes, bpm } = asset!;
    validatePcm(pcm);
    if (pcm.channels.length === 2) minimumChannels = 2;
    const start = secondsToFrame(root.source.start_s - origin) / SAMPLE_RATE;
    const end = secondsToFrame(root.source.end_s - origin) / SAMPLE_RATE;
    clips.set(root.id, {
      pcm: ops.trim(pcm, start, end), bpm, tempoBpm: bpm,
      beatTimes: mapBeatTimes(beatTimes, root.source.start_s, root.source.end_s).map((time) => secondsToFrame(time) / SAMPLE_RATE),
    });
    leaves.push(root.id);
  }
  const requireLeaf = (id: string): EvaluatedClip => {
    if (sliced.has(id)) throw new AudioEngineError("clip_is_sliced", `${id} has been sliced; select a child clip.`);
    return clips.get(id) ?? fail(`Clip ${id} does not exist.`);
  };
  const checkOrder = (replacement?: { id: string; frames: number }) => {
    let frames = 0;
    for (const id of order.length ? order : leaves) frames += id === replacement?.id ? replacement.frames : requireLeaf(id).pcm.channels[0].length;
    allocationBytes(frames, minimumChannels);
  };
  // A baseline may name a root that a later slice expands in place.
  checkOrder();
  for (const op of state.ops) {
    if (op.op === "arrange") {
      if (!op.order.length) fail("An arrangement needs at least one clip.");
      op.order.forEach(requireLeaf);
      order = [...op.order];
      checkOrder();
      continue;
    }
    const current = requireLeaf(op.clip);
    const { pcm, bpm } = current;
    const length = duration(pcm);
    let beatTimes = [...current.beatTimes];
    let tempoBpm = current.tempoBpm;
    let result: PcmBuffer;
    switch (op.op) {
      case "slice": {
        const cuts = [0, ...resolveCuts(pcm, op, current), pcm.channels[0].length];
        const children = cuts.slice(0, -1).map((first, index) => {
          const id = `${op.clip}.${index + 1}`;
          if (clips.has(id)) fail(`Slice ID ${id} already exists.`);
          const start = first / SAMPLE_RATE;
          const end = cuts[index + 1] / SAMPLE_RATE;
          clips.set(id, { pcm: ops.trim(pcm, start, end), bpm, tempoBpm,
            beatTimes: mapBeatTimes(beatTimes, start, end) });
          return id;
        });
        sliced.add(op.clip);
        leaves = leaves.flatMap((id) => id === op.clip ? children : [id]);
        order = order.flatMap((id) => id === op.clip ? children : [id]);
        checkOrder();
        continue;
      }
      case "trim": {
        result = ops.trim(pcm, op.start_s, op.end_s);
        const start = secondsToFrame(op.start_s) / SAMPLE_RATE;
        beatTimes = mapBeatTimes(beatTimes, start, start + duration(result));
        break;
      }
      case "reverse":
        result = ops.reverse(pcm);
        beatTimes = beatTimes.map((time) => (pcm.channels[0].length - secondsToFrame(time)) / SAMPLE_RATE)
          .filter((time) => time < length).sort((a, b) => a - b);
        break;
      case "gain": result = ops.gain(pcm, op.db); break;
      case "fade_in": result = ops.fadeIn(pcm, op.ms); break;
      case "fade_out": result = ops.fadeOut(pcm, op.ms); break;
      case "normalize": result = ops.normalize(pcm, op.peak_db); break;
      case "loop":
        checkOrder({ id: op.clip, frames: pcm.channels[0].length * op.times });
        result = ops.loop(pcm, op.times);
        beatTimes = Array.from({ length: op.times }, (_, index) => beatTimes.map((beat) => beat + index * length)).flat();
        break;
      default:
        if (!offline) fail(`${op.op} is unavailable in this session.`);
        const plan = planOfflineFrames(pcm, op, bpm);
        checkOrder({ id: op.clip, frames: plan.frames });
        result = await offline!(pcm, op, bpm);
        validatePcm(result);
        if (result.channels[0].length !== plan.frames || result.channels.length !== pcm.channels.length) {
          fail("Offline renderer returned unexpected frames or channels.");
        }
        beatTimes = beatTimes.map((time) => Math.round(time * duration(result) / length * SAMPLE_RATE) / SAMPLE_RATE)
          .filter((time) => time < duration(result));
        if (tempoBpm != null) tempoBpm *= plan.rate;
    }
    clips.set(op.clip, { pcm: result, bpm, tempoBpm, beatTimes });
    checkOrder();
  }
  const finalOrder = order.length ? order : leaves;
  return { clips, leaves, order: finalOrder, sliced,
    rendered: concatenate(finalOrder.map((id) => requireLeaf(id).pcm), minimumChannels) };
}
