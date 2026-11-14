import { createStore } from "zustand/vanilla";
import type { EditorState, Op } from "@/lib/types/api";
import { evaluate, type Evaluation, type SourceRegistry } from "@/lib/audio/evaluate";
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
  apply: (ops: Op[]) => Promise<void>;
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
export function createEditorStore() {
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
    const run = async (wire: EditorState, registry: SourceRegistry, initialize: boolean) => {
      const revision = get().revision + 1;
      const before = get().current;
      set({ revision, pending: true, error: null });
      try {
        const evaluation = await evaluate(registry, wire);
        if (get().revision !== revision) return;
        publish({ wire, registry, evaluation }, {
          past: initialize || !before ? [] : [...get().past, before], future: [],
        });
      } catch (error) {
        if (get().revision === revision) set({ pending: false,
          error: error instanceof Error ? error.message : "Audio edit failed." });
      }
    };
    return {
      ...initial,
      initialize: (wire, registry) => run(structuredClone(wire), registry, true),
      apply: async (ops) => {
        const { current, pending } = get();
        if (!current || pending || !ops.length) return;
        await run({ ...current.wire, ops: [...current.wire.ops, ...structuredClone(ops)] }, current.registry, false);
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
