"use client";

import { LOCAL_ACCEPT } from "@/lib/audio/source-import";

export function LocalFileDrop({ disabled, onFile, onError }: { disabled: boolean; onFile: (file: File) => void; onError: (message: string) => void }) {
  const receive = (files: FileList | null) => {
    if (!disabled && files && files.length > 1) { onError("Add one audio file at a time."); return; }
    if (!disabled && files?.length) onFile(files[0]);
  };
  return <section aria-label="Add local audio" className="space-y-2 rounded-lg border border-dashed p-4"
    onDragOver={(event) => { if (event.dataTransfer.types.includes("Files")) { event.preventDefault(); event.dataTransfer.dropEffect = disabled ? "none" : "copy"; } }}
    onDrop={(event) => { event.preventDefault(); receive(event.dataTransfer.files); }}>
    <label className="block text-sm font-medium">Drop one audio file here or choose a file
      <input className="mt-2 block w-full" type="file" accept={LOCAL_ACCEPT} disabled={disabled}
        onChange={(event) => { receive(event.target.files); event.target.value = ""; }} />
    </label>
    <p className="text-muted-foreground text-sm">WAV, MP3, FLAC, M4A or OGG · up to 25 MB and 60 seconds · stays on this device. Adds after existing clips. Exports at 44.1 kHz.</p>
  </section>;
}
