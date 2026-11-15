"use client";

import { useState } from "react";
import type { Stem, TrackDetail } from "@/lib/types/api";
import { coveringStems } from "@/lib/audio/source-import";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useEditorStemJob, useEditorStems } from "./stem-hooks";

interface Props {
  detail: TrackDetail;
  start: number;
  end: number;
  disabled: boolean;
  error: string | null;
  onSelect: (stem: Stem) => Promise<boolean>;
}
/** Editor-owned adapter; replace with WS3's StemsDrawer once that component lands. */
export function StemsDrawer({ detail, start, end, disabled, error, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const request = useEditorStems(detail.track.id, { start_s: start, end_s: end });
  const job = useEditorStemJob(request.data?.job_id ?? null, open);
  const output = job.data?.status === "done" && job.data.output && "stems" in job.data.output ? job.data.output.stems : [];
  const stems = coveringStems([...detail.stems, ...(request.data?.stems ?? []), ...output], detail.track.id, start, end);
  const waiting = !!request.data?.job_id && !job.isError && job.data?.status !== "error" && job.data?.status !== "done";
  const failed = request.error?.message ?? job.error?.message ?? (job.data?.status === "error" ? job.data.error ?? "Stem separation failed." : null);
  const empty = request.isSuccess && !waiting && !failed && !stems.length;
  const choose = async (stem: Stem) => { if (await onSelect(stem)) setOpen(false); };
  return <Sheet open={open} onOpenChange={setOpen}>
    <SheetTrigger asChild><Button variant="outline" disabled={disabled}>Stems</Button></SheetTrigger>
    <SheetContent className="overflow-y-auto">
      <SheetHeader><SheetTitle>Add a stem</SheetTitle><SheetDescription>
        {detail.track.title} · {start}–{end} s. Adds a clip after your arrangement; undo removes it.
      </SheetDescription></SheetHeader>
      <div className="space-y-4 px-4">
        <p className="text-sm">{detail.track.license} · {detail.track.attribution}</p>
        {stems.map((stem) => <Button key={stem.stem} className="mr-2" disabled={disabled || request.isPending} onClick={() => void choose(stem)}>Add {stem.stem}</Button>)}
        <p className="text-sm">{stems.length ? "Available stems cover this window. Request separation to check for more." : "No covering stems yet. Request separation for this window."}</p>
        <Button disabled={disabled || request.isPending || waiting} onClick={() => request.mutate()}>
          {request.isPending ? "Requesting…" : failed || empty ? "Retry separation" : "Request stems"}
        </Button>
        {waiting && <p role="status">{job.data?.status === "running" ? "Separating" : "Queued"} · {Math.round(Math.max(0, Math.min(1, job.data?.progress ?? 0)) * 100)}%</p>}
        {failed && <p role="alert">{failed}</p>}
        {error && <p role="alert">{error}</p>}
        {empty && <p role="alert">No returned stems cover this window. Retry separation or choose another range.</p>}
        {job.isError && <Button variant="outline" onClick={() => void job.refetch()}>Retry job status</Button>}
      </div>
    </SheetContent>
  </Sheet>;
}
