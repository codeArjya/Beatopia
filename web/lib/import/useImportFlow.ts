"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { keys, useImport, useJob } from "@/lib/api";

import { importFlowState, type ImportFlowState } from "./flow";

export type ImportFlow = ImportFlowState & {
  jobId: string | null;
  /** Upload a file that already passed the client checks. */
  start: (file: File) => void;
  /** Back to the empty drop zone. */
  reset: () => void;
};

/**
 * POST /imports, then poll the analyze job every second. When it's done, the finished `TrackDetail` is written
 * into `["track", id]` so the editor opens without another request.
 */
export function useImportFlow(): ImportFlow {
  const qc = useQueryClient();
  const upload = useImport();
  const jobId = upload.data?.job_id ?? null;
  const jobQ = useJob(jobId);
  const state = importFlowState(upload, jobQ);

  const seeded = useRef<string | null>(null);
  useEffect(() => {
    if (state.status !== "done" || !state.track || seeded.current === state.track.track.id) return;
    seeded.current = state.track.track.id;
    qc.setQueryData(keys.track(state.track.track.id), state.track);
  }, [qc, state.status, state.track]);

  const reset = () => {
    // Drop the old job from the cache: fixture mode reuses one job id, and a stale "done" would skip the progress.
    if (jobId) qc.removeQueries({ queryKey: keys.job(jobId), exact: true });
    seeded.current = null;
    upload.reset();
  };

  return {
    ...state,
    jobId,
    start: (file) => {
      reset();
      upload.mutate(file);
    },
    reset,
  };
}
