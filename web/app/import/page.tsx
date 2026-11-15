import type { Metadata } from "next";

import { ImportFlow } from "@/components/import/ImportFlow";

export const metadata: Metadata = { title: "Import · Beatopia" };

export default function ImportPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-10 sm:px-6 sm:py-16">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Import a track</h1>
        <p className="text-muted-foreground">
          Bring your own audio. We find its tempo, key and the best loop windows, then you can chop it in the editor.
          Imports stay private to you and never show up in search.
        </p>
      </div>
      <ImportFlow />
    </main>
  );
}
