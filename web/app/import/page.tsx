import type { Metadata } from "next";

export const metadata: Metadata = { title: "Import · Beatopia" };

// Stub: the drop zone lands in T7.1 (ImportDropzone).
export default function ImportPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 px-4 py-16 sm:px-6">
      <h1 className="text-2xl font-semibold tracking-tight">Import a track</h1>
      <p className="text-muted-foreground">
        Drop your own audio file (WAV, MP3, FLAC, M4A or OGG, up to 25 MB) to analyze it and open it in the editor.
        Coming soon.
      </p>
    </main>
  );
}
