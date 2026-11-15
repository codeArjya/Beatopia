import { createStore } from "zustand/vanilla";
import type { AssistRequest, AssistResponse, ChatMessage } from "@/lib/types/api";
import { assistRequest, assistResponse, assistUnavailable } from "@/lib/audio/assist";
import type { Evaluation } from "@/lib/audio/evaluate";
import type { EditorStoreApi } from "./editor";

interface Proposal {
  response: AssistResponse;
  revision: number;
  evaluation: Evaluation;
}
interface AssistStore {
  messages: ChatMessage[];
  pending: boolean;
  proposal: Proposal | null;
  error: string | null;
  retryMessages: ChatMessage[] | null;
  notice: string | null;
  send: (text: string) => Promise<void>;
  retry: () => Promise<void>;
  apply: () => Promise<boolean>;
  discard: () => void;
  clear: () => void;
}

export function createAssistStore(editor: EditorStoreApi, request: (body: AssistRequest) => Promise<AssistResponse>) {
  let generation = 0;
  return createStore<AssistStore>((set, get) => {
    const run = async (messages: ChatMessage[]) => {
      if (get().pending || editor.getState().pending) return;
      const token = ++generation;
      set({ messages, pending: true, proposal: null, error: null, retryMessages: null, notice: null });
      try {
        const state = editor.getState();
        const unavailable = assistUnavailable(state.toEditorState());
        if (unavailable) throw new Error(unavailable);
        const revision = state.revision;
        const body = assistRequest(messages, state.toEditorState()!);
        const response = assistResponse(await request(body));
        if (generation !== token) return;
        if (editor.getState().revision !== revision) throw new Error("The editor changed. Request a new suggestion.");
        const evaluation = await editor.getState().preview(response.ops, revision);
        if (generation !== token) return;
        set({ messages: [...messages, { role: "assistant", content: response.reply }], pending: false,
          proposal: response.ops.length ? { response, revision, evaluation } : null,
          notice: response.ops.length ? "Preview only. Apply commits all proposed edits as one undo step." : "Assist proposed no edits. Your audio is unchanged." });
      } catch (error) {
        if (generation === token) set({ pending: false, error: error instanceof Error ? error.message : "Assist is unavailable.", retryMessages: messages });
      }
    };
    return {
      messages: [], pending: false, proposal: null, error: null, retryMessages: null, notice: null,
      send: async (text) => {
        if (!text.trim() || get().pending || get().proposal) return;
        await run([...get().messages, { role: "user", content: text.trim() }]);
      },
      retry: async () => { const messages = get().retryMessages; if (messages) await run(messages); },
      apply: async () => {
        const proposal = get().proposal;
        if (!proposal || get().pending) return false;
        if (editor.getState().revision !== proposal.revision || editor.getState().pending) {
          set({ error: "The editor changed. Discard this preview and request a new suggestion." });
          return false;
        }
        const token = ++generation;
        set({ pending: true, error: null });
        const applied = await editor.getState().apply(proposal.response.ops, proposal.revision);
        if (generation !== token) return applied;
        set({ pending: false, proposal: applied ? null : proposal,
          error: applied ? null : editor.getState().error ?? "The editor changed. Request a new suggestion.",
          notice: applied ? "Applied suggestion. Undo restores the whole batch." : null });
        return applied;
      },
      discard: () => { if (get().pending) return; ++generation; set({ proposal: null, error: null, notice: "Discarded preview. Your audio is unchanged." }); },
      clear: () => { ++generation; set({ messages: [], pending: false, proposal: null, error: null, retryMessages: null, notice: null }); },
    };
  });
}
