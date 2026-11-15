// Pure rules for the result card's "why this works as a sample" note (T4.1).
import type { PreviewStatus } from "@/lib/preview/player";

/**
 * - `prompt`: no note yet and nothing has asked for one (a button invites the user to load it).
 * - `loading`: asked for, waiting on POST /why.
 * - `note`: text to show (cached on the result or fetched).
 * - `error`: the fetch failed; show an inline retry.
 */
export type WhyView = "prompt" | "loading" | "note" | "error";

export function whyView(s: { note: string | null | undefined; requested: boolean; isError: boolean }): WhyView {
  if (s.note) return "note";
  if (!s.requested) return "prompt";
  return s.isError ? "error" : "loading";
}

/**
 * A missing note is fetched on the first expand or the first play of that card, never on scroll (saves Gemini
 * calls). Once requested it stays requested.
 */
export function shouldRequestWhy(requested: boolean, expanded: boolean, preview: PreviewStatus): boolean {
  return requested || expanded || preview === "playing" || preview === "loading";
}
