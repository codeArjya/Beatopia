"use client";

import { mutationOptions, queryOptions, useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { Job, StemsRequest } from "@/lib/types/api";

// Reviewed fallback until WS3 supplies useStems/useJob. All HTTP remains in its typed client.
export function useEditorStems(trackId: string, range: StemsRequest) {
  return useMutation(stemRequestOptions(trackId, range));
}
export function stemRequestOptions(trackId: string, range: StemsRequest) {
  return mutationOptions({ mutationFn: () => api.requestStems(trackId, range), retry: false });
}

export function stemJobOptions(jobId: string | null, enabled: boolean) {
  return queryOptions({
    queryKey: ["job", jobId], queryFn: async () => {
      const job = await api.getJob(jobId!);
      if (job.id !== jobId || job.kind !== "stems") throw new Error("The API returned a different stem job.");
      return job;
    }, enabled: enabled && !!jobId, retry: false,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => stemPollInterval(query.state.data, query.state.error),
  });
}
export function stemPollInterval(job?: Job, error?: Error | null): number | false {
  return error || job?.status === "done" || job?.status === "error" ? false : 1000;
}
export function useEditorStemJob(jobId: string | null, enabled: boolean) {
  return useQuery(stemJobOptions(jobId, enabled));
}
