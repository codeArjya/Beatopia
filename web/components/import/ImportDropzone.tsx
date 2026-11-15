"use client";

import { cn } from "cn";
import { FileAudioIcon, TriangleAlertIcon } from "lucide-react";
import { useEffect, useId, useState, type DragEvent } from "react";

import { formatMB, IMPORT_ACCEPT, MAX_IMPORT_BYTES } from "@/lib/import/validate";

export type ImportDropzoneProps = {
  onFile: (file: File) => void;
  disabled?: boolean;
  /** Validation or upload error shown under the zone. */
  error?: string | null;
};

/**
 * Drop a file here or click (Enter/Space) to browse. The real `<input type=file>` sits inside the label as
 * sr-only, so the zone is one keyboard stop and the native picker opens on click. Validation happens in the
 * parent; this only hands over the first file.
 */
export function ImportDropzone({ onFile, disabled = false, error }: ImportDropzoneProps) {
  const [over, setOver] = useState(false);
  const hintId = useId();
  const errorId = useId();

  // A file dropped beside the zone would make the browser navigate to it; swallow those drops on this page.
  useEffect(() => {
    const block = (e: globalThis.DragEvent) => {
      if (e.dataTransfer?.types.includes("Files")) e.preventDefault();
    };
    window.addEventListener("dragover", block);
    window.addEventListener("drop", block);
    return () => {
      window.removeEventListener("dragover", block);
      window.removeEventListener("drop", block);
    };
  }, []);

  const hasFiles = (e: DragEvent) => e.dataTransfer.types.includes("Files");

  return (
    <div className="space-y-2">
      <label
        onDragEnter={(e) => {
          if (disabled || !hasFiles(e)) return;
          e.preventDefault();
          setOver(true);
        }}
        onDragOver={(e) => {
          if (disabled || !hasFiles(e)) return;
          e.preventDefault();
          e.dataTransfer.dropEffect = "copy";
        }}
        onDragLeave={(e) => {
          // Leaving into a child still counts as inside.
          if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          const file = e.dataTransfer.files[0];
          if (!disabled && file) onFile(file);
        }}
        className={cn(
          "flex min-h-56 cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-8 text-center transition-colors",
          "focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50",
          over ? "border-primary bg-primary/5" : "border-input hover:border-text-secondary hover:bg-card",
          error && !over && "border-destructive/60",
          disabled && "pointer-events-none cursor-default opacity-60",
        )}
      >
        <FileAudioIcon className={cn("size-10 text-muted-foreground", over && "text-primary-strong")} aria-hidden />
        <span className="text-base font-medium">{over ? "Drop to import" : "Drop an audio file here, or click to browse"}</span>
        <span id={hintId} className="text-sm text-muted-foreground">
          WAV, MP3, FLAC, M4A or OGG, up to {formatMB(MAX_IMPORT_BYTES)}
        </span>
        <input
          type="file"
          accept={IMPORT_ACCEPT}
          className="sr-only"
          disabled={disabled}
          aria-describedby={error ? `${hintId} ${errorId}` : hintId}
          aria-invalid={error ? true : undefined}
          onChange={(e) => {
            const file = e.currentTarget.files?.[0];
            e.currentTarget.value = ""; // so picking the same file again still fires change
            if (file) onFile(file);
          }}
        />
      </label>
      {error && (
        <p id={errorId} role="alert" className="flex items-start gap-2 text-sm text-destructive">
          <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}
