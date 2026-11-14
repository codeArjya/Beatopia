import { Suspense } from "react";

import { EditorPlaceholder } from "./editor-placeholder";

// Placeholder editor route (WS4 builds the real one).
// Entry URL: /editor?track={track_id}&start={start_s}&end={end_s}&stem={stem}
export default function EditorPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-4 px-6 py-24">
      <h1 className="text-3xl font-semibold tracking-tight">Editor</h1>
      <Suspense fallback={<p className="text-muted-foreground">Loading…</p>}>
        <EditorPlaceholder />
      </Suspense>
    </main>
  );
}
