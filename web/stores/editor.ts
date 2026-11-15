import { createStore } from "zustand/vanilla";
import type { ClipSource, EditorState, Op } from "@/lib/types/api";
import { evaluate, sourceKey, type SourceAsset, type Evaluation, type SourceRegistry, type OfflineRenderer } from "@/lib/audio/evaluate";
import { duration } from "@/lib/audio/pcm";

interface Checkpoint {
  wire: EditorState;
  registry: SourceRegistry;
  evaluation: Evaluation;
}
interface EditorStore {
  current: Checkpoint | null;
  past: Checkpoint[];
  future: Checkpoint[];
  active: string | null;
  selection: [number, number] | null;
  revision: number;
  pending: boolean;
  error: string | null;
  initialize: (wire: EditorState, registry: SourceRegistry) => Promise<void>;
  apply: (ops: Op[], expectedRevision?: number) => Promise<boolean>;
  preview: (ops: Op[], expectedRevision: number) => Promise<Evaluation>;
  addSource: (source: ClipSource, asset: SourceAsset, expectedRevision?: number) => Promise<boolean>;
  undo: () => void;
  redo: () => void;
  select: (id: string) => void;
  setSelection: (range: [number, number]) => void;
  reset: () => void;
  toEditorState: () => EditorState | null;
}
const initial = {
  current: null, past: [], future: [], active: null, selection: null,
  revision: 0, pending: false, error: null,
};
export function createEditorStore(offline?: OfflineRenderer) {
  return createStore<EditorStore>((set, get) => {
    const publish = (checkpoint: Checkpoint, extra: Partial<EditorStore> = {}) => {
      const previous = get().active;
      const active = previous && checkpoint.evaluation.leaves.includes(previous)
        ? previous : checkpoint.evaluation.leaves.find((id) => previous && id.startsWith(`${previous}.`))
          ?? checkpoint.evaluation.leaves[0] ?? null;
      const pcm = active ? checkpoint.evaluation.clips.get(active)?.pcm : null;
      set({ current: checkpoint, active, selection: pcm ? [0, duration(pcm)] : null,
        pending: false, error: null, ...extra });
    };
    const run = async (wire: EditorState, registry: SourceRegistry, initialize: boolean): Promise<boolean> => {
      const revision = get().revision + 1;
      const before = get().current;
      set({ revision, pending: true, error: null });
      try {
        const evaluation = await evaluate(registry, wire, offline);
        if (get().revision !== revision) return false;
        publish({ wire, registry, evaluation }, {
          past: initialize || !before ? [] : [...get().past, before], future: [],
        });
        return true;
      } catch (error) {
        if (get().revision === revision) set({ pending: false,
          error: error instanceof Error ? error.message : "Audio edit failed." });
        return false;
      }
    };
    return {
      ...initial,
      initialize: async (wire, registry) => { await run(structuredClone(wire), registry, true); },
      preview: async (ops, expectedRevision) => {
        const { current, pending, revision } = get();
        if (!current || pending || revision !== expectedRevision) throw new Error("The editor changed. Request a new suggestion.");
        const evaluation = await evaluate(current.registry,
          { ...current.wire, ops: [...current.wire.ops, ...structuredClone(ops)] }, offline);
        if (get().revision !== expectedRevision) throw new Error("The editor changed. Request a new suggestion.");
        return evaluation;
      },
      apply: async (ops, expectedRevision = get().revision) => {
        const { current, pending, revision } = get();
        if (!current || pending || !ops.length || revision !== expectedRevision) return false;
        return run({ ...current.wire, ops: [...current.wire.ops, ...structuredClone(ops)] }, current.registry, false);
      },
      addSource: async (source, asset, expectedRevision = get().revision) => {
        const { current, pending, revision } = get();
        if (pending || revision !== expectedRevision) return false;
        let index = 1;
        while (current?.wire.clips.some((clip) => clip.id === `c${index}`)) index++;
        const clip = { id: `c${index}`, source: structuredClone(source) };
        const registry = new Map(current?.registry);
        registry.set(sourceKey(source), asset);
        const wire: EditorState = current ? {
          ...current.wire, clips: [...current.wire.clips, clip],
          // An explicit arrangement may omit new roots. Append after the existing audible order.
          ops: [...current.wire.ops, { op: "arrange", order: [...current.evaluation.order, clip.id] }],
        } : { bpm: asset.bpm, clips: [clip], ops: [], arrangement: [] };
        const added = await run(wire, registry, !current);
        if (added) get().select(clip.id);
        return added;
      },
      undo: () => {
        const { past, current, future, pending } = get();
        if (pending || !past.length || !current) return;
        publish(past[past.length - 1], { past: past.slice(0, -1), future: [current, ...future], revision: get().revision + 1 });
      },
      redo: () => {
        const { past, current, future, pending } = get();
        if (pending || !future.length || !current) return;
        publish(future[0], { past: [...past, current], future: future.slice(1), revision: get().revision + 1 });
      },
      select: (id) => {
        const pcm = get().current?.evaluation.leaves.includes(id) && get().current?.evaluation.clips.get(id)?.pcm;
        if (pcm) set({ active: id, selection: [0, duration(pcm)] });
      },
      setSelection: (range) => {
        const active = get().active;
        const pcm = active && get().current?.evaluation.clips.get(active)?.pcm;
        if (pcm && range.every(Number.isFinite) && range[0] >= 0 && range[0] < range[1] && range[1] <= duration(pcm)) {
          set({ selection: range });
        }
      },
      reset: () => set({ ...initial, revision: get().revision + 1 }),
      toEditorState: () => get().current ? structuredClone(get().current!.wire) : null,
    };
  });
}
export type EditorStoreApi = ReturnType<typeof createEditorStore>;
