"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { keys, useJob, useStems } from "@/lib/api";

import { clampStemsRange, stemsFlowState, type StemsFlowState } from "./flow";

export type StemsFlow = StemsFlowState & { retry: () => void };

/**
 * Stems for a window: POST /tracks/{id}/stems (a query, so it can't queue twice), then poll the job if one was
 * queued. Ranges are clamped to 60 s. When the job finishes, `["track", id]` is invalidated so the editor sees
 * the new stem rows. `enabled: false` (drawer closed) sends nothing.
 */
export function useStemsFlow(trackId: string, start: number, end: number, enabled = true): StemsFlow {
  const qc = useQueryClient();
  const req = enabled ? clampStemsRange(start, end) : null;
  const stemsQ = useStems(trackId, req);
  const jobId = stemsQ.data && !stemsQ.data.stems?.length ? (stemsQ.data.job_id ?? null) : null;
  const jobQ = useJob(jobId);

  const jobDone = jobQ.data?.status === "done";
  useEffect(() => {
    if (jobDone) void qc.invalidateQueries({ queryKey: keys.track(trackId) });
  }, [jobDone, qc, trackId]);

  const retry = () => {
    // Reset (not just refetch) the job first: a finished/failed job has stopped polling, and a re-request may
    // hand back the same job id. Then ask for stems again, which may queue a fresh job.
    if (jobId) void qc.resetQueries({ queryKey: keys.job(jobId), exact: true });
    if (req) void qc.resetQueries({ queryKey: keys.stems(trackId, req), exact: true });
  };

  return { ...stemsFlowState(req !== null, stemsQ, jobQ), retry };
}
