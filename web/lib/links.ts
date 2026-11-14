// App URLs built in one place. The editor hand-off URL is fixed by the WS3 handoff:
// /editor?track={track_id}&start={start_s}&end={end_s}&stem={stem}

import type { StemName } from "@/lib/types/api";

export type EditorLink = { track: string; start: number; end: number; stem: StemName };

/** Seconds as short as possible, at most millisecond precision ("10.667", "0", "5.5"). */
export function formatSeconds(s: number): string {
  const v = Math.round(s * 1000) / 1000;
  return Object.is(v, -0) ? "0" : String(v);
}

export function editorHref({ track, start, end, stem }: EditorLink): string {
  const q = new URLSearchParams({ track, start: formatSeconds(start), end: formatSeconds(end), stem });
  return `/editor?${q.toString()}`;
}
