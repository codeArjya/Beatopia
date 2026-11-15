import type { EditorStoreApi } from "@/stores/editor";
import { describeOp } from "@/lib/audio/editor-actions";

export function HistoryPanel({ editor }: { editor: ReturnType<EditorStoreApi["getState"]> }) {
  const checkpoints = [...editor.past, ...(editor.current ? [editor.current] : []), ...editor.future];
  return <section aria-label="Edit history" className="space-y-2 rounded-lg border p-4">
    <h3 className="font-medium">History · {editor.past.length} applied steps</h3>
    <ol className="max-h-48 space-y-1 overflow-auto text-sm">
      <li>Original source</li>
      {checkpoints.slice(1).map((checkpoint, index) => <li key={index} className={index >= editor.past.length ? "text-muted-foreground" : undefined}>
        {index + 1}. {checkpoint.wire.clips.slice(checkpoints[index].wire.clips.length).map((clip) => `Add ${clip.id} (${clip.source.track_id === "local" ? "local file" : clip.source.stem ?? "mix"})`).join("; ")}
        {checkpoint.wire.clips.length > checkpoints[index].wire.clips.length ? " · " : ""}
        {checkpoint.wire.ops.slice(checkpoints[index].wire.ops.length).map(describeOp).join("; ")}
        {index >= editor.past.length ? " (undone)" : ""}
      </li>)}
    </ol>
  </section>;
}
