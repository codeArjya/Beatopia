"use client";

import { queryOptions, skipToken, useQuery } from "@tanstack/react-query";

import { keys } from "@/lib/api/keys";

import { channelsOf, decodeAudio } from "./decode";
import { computePeaks, PEAK_BUCKETS } from "./peaks";

/** Raw peaks of [start, end] in `url`. `enabled: false` (card not on screen yet) = no fetch. */
export const peaksQuery = (url: string, start: number, end: number, enabled: boolean) =>
  queryOptions({
    queryKey: keys.peaks(url, start, end),
    queryFn: enabled
      ? async () => {
          const buffer = await decodeAudio(url);
          return computePeaks({ channels: channelsOf(buffer), sampleRate: buffer.sampleRate }, start, end, PEAK_BUCKETS);
        }
      : skipToken,
    staleTime: Infinity,
    gcTime: 30 * 60_000,
    // A CORS or decode failure won't fix itself; the card shows the flat placeholder.
    retry: false,
  });

export function usePeaks(url: string, start: number, end: number, enabled: boolean) {
  return useQuery(peaksQuery(url, start, end, enabled));
}
