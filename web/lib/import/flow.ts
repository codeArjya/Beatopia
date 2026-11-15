// Pure rules for the import page (T7.1/T7.2): upload error text, the upload → analyze → done state machine,
// and which window the "Open in editor" button uses.
import { ApiError } from "@/lib/api/client";
import type { EditorLink } from "@/lib/links";
import type { ImportResponse, Job, TrackDetail } from "@/lib/types/api";

/** Message for a failed POST /imports. The server's own message is shown for format errors (it's specific). */
export function importErrorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    switch (e.code) {
      case "upload_too_large":
        return "That file is over the 25 MB limit.";
      case "unsupported_format":
        return `The server couldn't read that file: ${e.message}.`;
      case "bad_request":
        return `The upload was rejected: ${e.message}.`;
      case "timeout":
        return "The upload took too long. Check your connection and try again.";
      case "network_error":
        return "Couldn't reach the server. Check your connection and try again.";
      default:
        return e.message ? `Import failed: ${e.message}.` : "Import failed. Try again.";
    }
  }
  return "Import failed. Try again.";
}

export type ImportFlowStatus = "idle" | "uploading" | "queued" | "analyzing" | "done" | "error";

export type ImportFlowState = {
  status: ImportFlowStatus;
  /** 0..1 analysis progress (null while uploading: unknown). */
  progress: number | null;
  track: TrackDetail | null;
  error: string | null;
  /** Which step failed, so the page can offer the right retry. */
  failedAt: "upload" | "analyze" | null;
};

type UploadLike = { status: "idle" | "pending" | "success" | "error"; error: unknown; data: ImportResponse | undefined };
type QueryLike<T> = { data: T | undefined; error: Error | null };

const base: ImportFlowState = { status: "idle", progress: null, track: null, error: null, failedAt: null };

/** Upload mutation + polled analyze job → one page state. */
export function importFlowState(upload: UploadLike, jobQ: QueryLike<Job>): ImportFlowState {
  if (upload.status === "idle") return base;
  if (upload.status === "pending") return { ...base, status: "uploading" };
  if (upload.status === "error") return { ...base, status: "error", error: importErrorMessage(upload.error), failedAt: "upload" };

  const job = jobQ.data;
  if (job?.status === "error") {
    return { ...base, status: "error", error: job.error || "Analysis failed.", failedAt: "analyze" };
  }
  if (job?.status === "done") {
    const track = job.output && "track" in job.output ? job.output.track : null;
    return track
      ? { ...base, status: "done", progress: 1, track }
      : { ...base, status: "error", error: "Analysis finished without a result.", failedAt: "analyze" };
  }
  // A failed poll with no job yet is an error; once we have a job, polling keeps going through blips.
  if (jobQ.error && !job) {
    return { ...base, status: "error", error: jobQ.error.message || "Lost track of the analysis.", failedAt: "analyze" };
  }
  if (!job || job.status === "queued") return { ...base, status: "queued", progress: 0 };
  return { ...base, status: "analyzing", progress: clamp01(job.progress) };
}

const clamp01 = (x: number) => (Number.isFinite(x) ? Math.min(1, Math.max(0, x)) : 0);

/** Fallback window when analysis found none: 8 bars at the track's tempo (16 s if unknown), cut to the track. */
export const FALLBACK_BARS = 8;
const FALLBACK_SECONDS = 16;

/**
 * Editor hand-off for an imported track: the window with the highest loopability (ties → earliest), else
 * `0 → min(duration, 8 bars)`.
 */
export function importEditorLink(detail: TrackDetail): EditorLink {
  const id = detail.track.id;
  const best = [...detail.windows].sort((a, b) => b.loopability - a.loopability || a.start_s - b.start_s)[0];
  if (best) return { track: id, start: best.start_s, end: best.end_s, stem: best.stem };

  const bpm = detail.track.bpm;
  const span = bpm && bpm > 0 ? (FALLBACK_BARS * 4 * 60) / bpm : FALLBACK_SECONDS;
  const duration = detail.track.duration_s;
  return { track: id, start: 0, end: duration > 0 ? Math.min(duration, span) : span, stem: "mix" };
}
