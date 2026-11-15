// TanStack Query hooks for EVERY endpoint (CONTRACT §6). WS3 and WS4 both import these from "@/lib/api".
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getSessionId } from "@/lib/session";
import type { AssistRequest, EventRequest, StemsRequest } from "@/lib/types/api";

import { api } from "./client";
import { keys, type SearchParams } from "./keys";
import { chipsQuery, healthQuery, jobQuery, jobTrack, searchQuery, stemsQuery, trackQuery, whyQuery } from "./queries";

export const useHealth = () => useQuery(healthQuery());

export const useChips = () => useQuery(chipsQuery());

/** `null` = idle; previous results stay on screen while the next search loads (keepPreviousData). */
export const useSearch = (params: SearchParams | null) => useQuery(searchQuery(params));

/** GET /tracks/{id}; `null` id = disabled. */
export const useTrack = (id: string | null) => useQuery(trackQuery(id));

/** POST /tracks/{id}/stems; `null` request = not asked yet. Returns either `stems` or a `job_id` to poll. */
export const useStems = (trackId: string, req: StemsRequest | null) => useQuery(stemsQuery(trackId, req));

/** GET /jobs/{id}, polled every 1 s until done/error; `null` id = disabled. */
export const useJob = (id: string | null) => useQuery(jobQuery(id));

/** POST /why. Pass the search result's cached note so no request is made when it exists. */
export const useWhy = (windowId: string, opts: { cachedNote?: string | null; enabled?: boolean } = {}) =>
  useQuery({ ...whyQuery(windowId, opts.cachedNote), enabled: opts.enabled ?? true });

/** POST /imports (multipart). Poll the returned job_id with useJob; on done, the track is seeded into the cache. */
export function useImport() {
  return useMutation({ mutationFn: (file: File) => api.createImport(file, getSessionId()) });
}

/** Write a finished analyze job's track into ["track", id] so the editor opens without another request. */
export function useSeedTrackFromJob() {
  const qc = useQueryClient();
  return (job: Parameters<typeof jobTrack>[0]) => {
    const detail = jobTrack(job);
    if (detail) qc.setQueryData(keys.track(detail.track.id), detail);
    return detail;
  };
}

/** POST /events, fire-and-forget: failures are swallowed (analytics must never break the UI). */
export function usePostEvent() {
  const m = useMutation({
    mutationFn: (e: Omit<EventRequest, "session_id">) => api.postEvent({ ...e, session_id: getSessionId() }),
    retry: false,
  });
  return (e: Omit<EventRequest, "session_id">) => m.mutate(e, { onError: () => undefined });
}

/** POST /assist (editor chat). Append `data.ops` as one undo step. */
export const useAssist = () => useMutation({ mutationFn: (req: AssistRequest) => api.assist(req) });

export type { SearchParams };
