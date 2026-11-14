// queryOptions factories, one per GET-like endpoint. Hooks wrap these; tests run them with queryClient.fetchQuery.
import { keepPreviousData, queryOptions, skipToken } from "@tanstack/react-query";

import { getSessionId } from "@/lib/session";
import type { Job, Stem, StemsRequest, TrackDetail } from "@/lib/types/api";

import { api } from "./client";
import { keys, type SearchParams } from "./keys";

export const JOB_POLL_MS = 1000;

export const healthQuery = () => queryOptions({ queryKey: keys.health, queryFn: api.health, staleTime: 30_000 });

export const chipsQuery = () =>
  queryOptions({ queryKey: keys.chips, queryFn: api.getChips, staleTime: Infinity });

/** `null` params = idle (no text, no chips): the query is disabled via skipToken. */
export const searchQuery = (params: SearchParams | null) =>
  queryOptions({
    queryKey: keys.search(params),
    queryFn: params
      ? () => {
          // Dev-only request counter: one line per search actually sent (checks the 300 ms debounce).
          if (process.env.NODE_ENV === "development") console.debug("[search] request", params);
          return api.search({ text: params.text, chips: params.chips, limit: params.limit, session_id: getSessionId() });
        }
      : skipToken,
    placeholderData: keepPreviousData,
    staleTime: 5 * 60_000,
  });

export const trackQuery = (id: string | null) =>
  queryOptions({
    queryKey: keys.track(id),
    queryFn: id ? () => api.getTrack(id) : skipToken,
    staleTime: 5 * 60_000,
  });

/**
 * POST /tracks/{id}/stems as a query: it is idempotent for a given range, and retry:false + staleTime:Infinity
 * mean a re-render or retry can never queue a second separation job. `req: null` = not requested yet.
 */
export const stemsQuery = (trackId: string, req: StemsRequest | null) =>
  queryOptions({
    queryKey: keys.stems(trackId, req ?? { start_s: -1, end_s: -1 }),
    queryFn: req ? () => api.requestStems(trackId, req) : skipToken,
    retry: false,
    staleTime: Infinity,
  });

/** Poll every second until the job is done or failed. */
export function jobPollInterval(job: Job | undefined): number | false {
  return job && (job.status === "done" || job.status === "error") ? false : JOB_POLL_MS;
}

export const jobQuery = (id: string | null) =>
  queryOptions({
    queryKey: keys.job(id),
    queryFn: id ? () => api.getJob(id) : skipToken,
    refetchInterval: (q) => jobPollInterval(q.state.data),
    refetchIntervalInBackground: true,
    staleTime: 0,
  });

/** Stems from a finished stems job (Job.output is StemsJobOutput | AnalyzeJobOutput | null). */
export function jobStems(job: Job | undefined): Stem[] | null {
  return job?.output && "stems" in job.output ? job.output.stems : null;
}

/** Track from a finished analyze (import) job. */
export function jobTrack(job: Job | undefined): TrackDetail | null {
  return job?.output && "track" in job.output ? job.output.track : null;
}

/** POST /why as a query. A cached note from the search result (`Result.why`) seeds it, so no request is made. */
export const whyQuery = (windowId: string, cachedNote?: string | null) =>
  queryOptions({
    queryKey: keys.why(windowId),
    queryFn: () => api.why({ window_id: windowId }),
    initialData: cachedNote ? { window_id: windowId, note: cachedNote } : undefined,
    staleTime: Infinity,
  });
