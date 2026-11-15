"use client";

import { LoaderCircleIcon, RotateCwIcon, TriangleAlertIcon } from "lucide-react";
import { useState } from "react";

import { AppButton } from "@/components/adapters";
import { useStopPreviewOnHide } from "@/lib/preview/PreviewProvider";
import { STUCK_QUEUE_MS } from "@/lib/import/flow";
import { useImportFlow } from "@/lib/import/useImportFlow";
import { useSlow } from "@/lib/search/useSlow";
import { validateImportFile } from "@/lib/import/validate";

import { ImportDropzone } from "./ImportDropzone";
import { ImportSummary } from "./ImportSummary";

/** /import body: drop or pick a file → client checks → upload → poll analysis → summary + editor hand-off. */
export function ImportFlow() {
  const flow = useImportFlow();
  useStopPreviewOnHide();
  const [checkError, setCheckError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  // Nothing has claimed the job for a while: the worker may be down. Say so instead of spinning forever.
  const stuck = useSlow(flow.status === "queued", flow.jobId ?? "", STUCK_QUEUE_MS);

  const onFile = async (f: File) => {
    const check = await validateImportFile(f);
    if (!check.ok) {
      flow.reset();
      setFile(null);
      setCheckError(check.message);
      return;
    }
    setCheckError(null);
    setFile(f);
    flow.start(f);
  };

  const again = () => {
    flow.reset();
    setFile(null);
    setCheckError(null);
  };

  if (flow.status === "done" && flow.track) return <ImportSummary detail={flow.track} onAnother={again} />;

  const busy = flow.status === "uploading" || flow.status === "queued" || flow.status === "analyzing";
  if (busy) {
    const text =
      flow.status === "uploading"
        ? `Uploading ${file?.name ?? "your file"}…`
        : flow.status === "queued"
          ? "Uploaded. Waiting for the analyzer…"
          : "Finding tempo, key and loop windows…";
    return (
      <div role="status" aria-live="polite" className="space-y-3 rounded-xl border p-6">
        <p className="flex items-center gap-2 font-medium">
          <LoaderCircleIcon className="size-4 animate-spin" aria-hidden />
          {text}
        </p>
        <ProgressBar value={flow.status === "uploading" ? null : flow.progress} />
        <p className="text-xs text-muted-foreground">
          {file?.name} · analysis usually takes 10–30 seconds. Keep this tab open.
        </p>
        {stuck && (
          <p className="text-sm text-warning">
            The analyzer hasn&apos;t picked this up yet; it may be busy or offline. We&apos;ll keep checking.
          </p>
        )}
      </div>
    );
  }

  const uploadError = flow.status === "error" && flow.failedAt === "upload" ? flow.error : null;

  return (
    <div className="space-y-4">
      <ImportDropzone onFile={onFile} error={checkError ?? uploadError} />
      {uploadError && file && (
        <AppButton variant="outline" size="sm" onClick={() => flow.start(file)}>
          <RotateCwIcon aria-hidden />
          Retry upload of {file.name}
        </AppButton>
      )}
      {flow.status === "error" && flow.failedAt === "analyze" && (
        <div role="alert" className="space-y-3 rounded-lg border border-destructive/40 p-3 text-sm">
          <p className="flex items-start gap-2">
            <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
            <span>Couldn&apos;t analyze {file?.name ?? "that file"}. {flow.error}</span>
          </p>
          {file && (
            <AppButton size="sm" variant="outline" onClick={() => flow.start(file)}>
              <RotateCwIcon aria-hidden />
              Try again
            </AppButton>
          )}
        </div>
      )}
    </div>
  );
}

/** `value` null = indeterminate (upload in flight). */
function ProgressBar({ value }: { value: number | null }) {
  const pct = value == null ? null : Math.round(value * 100);
  return (
    <div
      role="progressbar"
      aria-label="Import progress"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct ?? undefined}
      className="h-1.5 w-full overflow-hidden rounded-full bg-secondary"
    >
      <div
        className={pct == null ? "h-full w-1/3 animate-pulse rounded-full bg-primary/60" : "h-full rounded-full bg-primary transition-[width] duration-200"}
        style={pct == null ? undefined : { width: `${Math.max(pct, 3)}%` }}
      />
    </div>
  );
}
