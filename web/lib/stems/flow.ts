// Pure rules for the stems drawer (T5.1/T5.2): range clamping, the ready-vs-job state machine, and the
// file-time offsets used to preview one stem through the shared player.
import type { PreviewItem } from "@/lib/preview/loop";
import type { Job, Stem, StemsRequest, StemsResponse } from "@/lib/types/api";

/** The API rejects longer ranges with `range_too_long`; the client clamps so that never happens. */
export const MAX_STEMS_RANGE_S = 60;

export function clampStemsRange(start: number, end: number): StemsRequest {
  const s = Math.max(0, start);
  return { start_s: s, end_s: Math.min(Math.max(end, s), s + MAX_STEMS_RANGE_S) };
}

export type StemsFlowStatus = "idle" | "requesting" | "queued" | "running" | "ready" | "error";

export type StemsFlowState = {
  status: StemsFlowStatus;
  /** 0..1; 1 when ready, the job's progress while separating. */
  progress: number;
  stems: Stem[] | null;
  error: string | null;
};

type QueryLike<T> = { data: T | undefined; error: Error | null };

/**
 * Combine the POST /stems answer and the polled job into one drawer state.
 * - stems in the response → ready at once (pre-separated hero track, or a range already done).
 * - job_id → "queued" until the first poll, then the job's status and progress; done → its `output.stems`.
 */
export function stemsFlowState(
  requested: boolean,
  stemsQ: QueryLike<StemsResponse>,
  jobQ: QueryLike<Job>,
): StemsFlowState {
  const idle = { progress: 0, stems: null, error: null };
  if (!requested) return { status: "idle", ...idle };
  if (stemsQ.error) return { status: "error", ...idle, error: stemsQ.error.message || "Couldn't request stems." };
  const res = stemsQ.data;
  if (!res) return { status: "requesting", ...idle };
  if (res.stems?.length) return { status: "ready", progress: 1, stems: res.stems, error: null };
  if (!res.job_id) return { status: "error", ...idle, error: "The server returned no stems and no job." };

  const job = jobQ.data;
  if (job?.status === "error") return { status: "error", ...idle, error: job.error || "Stem separation failed." };
  if (job?.status === "done") {
    const stems = job.output && "stems" in job.output ? job.output.stems : null;
    return stems?.length
      ? { status: "ready", progress: 1, stems, error: null }
      : { status: "error", ...idle, error: "The separation job finished without stems." };
  }
  // A failed poll keeps the last known job state; polling continues (refetchInterval) and retry is offered.
  if (jobQ.error && !job) return { status: "error", ...idle, error: jobQ.error.message || "Lost track of the job." };
  if (!job || job.status === "queued") return { status: "queued", ...idle, progress: job?.progress ?? 0 };
  return { status: "running", ...idle, progress: clamp01(job.progress) };
}

const clamp01 = (x: number) => (Number.isFinite(x) ? Math.min(1, Math.max(0, x)) : 0);

/**
 * Preview one stem of a window. Stem files start at `range_start_s` in track time, so the window maps to
 * `[start - range_start, end - range_start]` in file time, clamped to what the file covers.
 */
export function stemPreviewItem(stem: Stem, start: number, end: number): PreviewItem {
  const fileEnd = stem.range_end_s - stem.range_start_s;
  const s = Math.min(Math.max(0, start - stem.range_start_s), fileEnd);
  const e = Math.min(Math.max(s, end - stem.range_start_s), fileEnd);
  return {
    id: `stem:${stem.track_id}:${stem.stem}:${stem.range_start_s}-${stem.range_end_s}:${start}-${end}`,
    url: stem.url,
    start: s,
    end: e,
  };
}

/** Display order: drums, bass, vocals, then the rest (piano, guitar, other). */
const ORDER = ["drums", "bass", "vocals", "piano", "guitar", "other", "mix"] as const;
export function sortStems(stems: Stem[]): Stem[] {
  return [...stems].sort((a, b) => ORDER.indexOf(a.stem) - ORDER.indexOf(b.stem));
}
