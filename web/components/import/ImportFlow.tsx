"use client";

import { LoaderCircleIcon } from "lucide-react";
import { useState } from "react";

import { useImport } from "@/lib/api";
import { importErrorMessage } from "@/lib/import/flow";
import { validateImportFile } from "@/lib/import/validate";

import { ImportDropzone } from "./ImportDropzone";

/** /import body: drop or pick a file → client checks → POST /imports. */
export function ImportFlow() {
  const upload = useImport();
  const [checkError, setCheckError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  const onFile = async (file: File) => {
    setFileName(file.name);
    upload.reset();
    const check = await validateImportFile(file);
    if (!check.ok) {
      setCheckError(check.message);
      return;
    }
    setCheckError(null);
    upload.mutate(file);
  };

  const error = checkError ?? (upload.isError ? importErrorMessage(upload.error) : null);

  return (
    <div className="space-y-4">
      <ImportDropzone onFile={onFile} disabled={upload.isPending} error={error} />
      <div role="status" aria-live="polite" className="min-h-6 text-sm text-muted-foreground">
        {upload.isPending && (
          <p className="flex items-center gap-2">
            <LoaderCircleIcon className="size-4 animate-spin" aria-hidden />
            Uploading {fileName}…
          </p>
        )}
        {upload.isSuccess && <p>Uploaded {fileName}. Analyzing… (track {upload.data.track_id})</p>}
      </div>
    </div>
  );
}
