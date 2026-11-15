import { Suspense } from "react";

import { EditorClient } from "@/components/editor/editor-client";

// Entry URL: /editor?track={track_id}&start={start_s}&end={end_s}&stem={stem}
export default function EditorPage() {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 px-6 py-12">
      <h1 className="text-3xl font-semibold tracking-tight">Editor</h1>
      <Suspense fallback={<p className="text-muted-foreground">Loading…</p>}>
        <EditorClient />
      </Suspense>
    </main>
  );
}
