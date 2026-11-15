// Typed API client: one function per CONTRACT §6 endpoint. The only place in web/ that knows URLs.
// NEXT_PUBLIC_USE_FIXTURES=1 → answers come from shared/fixtures (no backend needed), else NEXT_PUBLIC_API_URL.
// WS3 owns this folder and builds the TanStack Query hooks on top of it.

import assistFixture from "@fixtures/assist.json";
import chipsFixture from "@fixtures/chips.json";
import importFixture from "@fixtures/import.json";
import jobDoneAnalyzeFixture from "@fixtures/job_done_analyze.json";
import jobDoneStemsFixture from "@fixtures/job_done_stems.json";
import jobRunningFixture from "@fixtures/job_running.json";
import searchFixture from "@fixtures/search.json";
import searchEmptyFixture from "@fixtures/search_empty.json";
import searchFallbackFixture from "@fixtures/search_fallback.json";
import stemsQueuedFixture from "@fixtures/stems_queued.json";
import stemsReadyFixture from "@fixtures/stems_ready.json";
import trackDetailFixture from "@fixtures/track_detail.json";
import whyFixture from "@fixtures/why.json";

import type {
  ApiError as ApiErrorBody,
  AssistRequest,
  AssistResponse,
  ChipsResponse,
  EventRequest,
  ImportResponse,
  Job,
  SearchRequest,
  SearchResponse,
  StemsRequest,
  StemsResponse,
  TrackDetail,
  WhyRequest,
  WhyResponse,
} from "@/lib/types/api";

export const USE_FIXTURES = process.env.NEXT_PUBLIC_USE_FIXTURES === "1";
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

/** Thrown for every non-2xx response; mirrors the `{"error": ApiError}` body. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Default per-request timeout. Search embeds the query with CLAP on a CPU VM, so leave room; uploads get more. */
export const REQUEST_TIMEOUT_MS = 20_000;
const UPLOAD_TIMEOUT_MS = 120_000;

async function request<T>(path: string, init?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, signal: AbortSignal.timeout(timeoutMs) });
  } catch (e) {
    // AbortSignal.timeout rejects with a DOMException named "TimeoutError"; anything else is the network.
    if (e instanceof Error && e.name === "TimeoutError") {
      throw new ApiError(0, "timeout", `no answer after ${Math.round(timeoutMs / 1000)} s`);
    }
    throw new ApiError(0, "network_error", e instanceof Error ? e.message : "network error");
  }
  if (!res.ok) {
    let body: { error?: ApiErrorBody } | undefined;
    try {
      body = (await res.json()) as { error?: ApiErrorBody };
    } catch {
      body = undefined;
    }
    throw new ApiError(res.status, body?.error?.code ?? "http_error", body?.error?.message ?? res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/** Resolve a fixture on the next tick with a small delay, so loading states are visible in fixture mode. */
function fixture<T>(data: unknown, delayMs = 150): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(structuredClone(data) as T), delayMs));
}

/**
 * Fixture-mode search. Dev-only switch: `?fixture=empty` or `?fixture=fallback` in the page URL serves
 * search_empty.json / search_fallback.json instead of search.json, to check those UI states in the browser.
 */
export function fixtureSearchVariant(): "default" | "empty" | "fallback" {
  if (typeof window === "undefined") return "default";
  const v = new URLSearchParams(window.location.search).get("fixture");
  return v === "empty" || v === "fallback" ? v : "default";
}

function fixtureSearch(): Promise<SearchResponse> {
  const v = fixtureSearchVariant();
  const data = v === "empty" ? searchEmptyFixture : v === "fallback" ? searchFallbackFixture : searchFixture;
  return fixture<SearchResponse>(data, 300);
}

// Fixture-mode job polling: a stems job reports "running" for the first 2 polls, then "done".
const fixturePolls = new Map<string, number>();
const FIXTURE_RUNNING_POLLS = 2;

// Fixture-mode stems: ready if every fixture stem covers the requested range, else queue the fixture job.
function fixtureStems(req: StemsRequest): Promise<StemsResponse> {
  const covered = stemsReadyFixture.stems.every(
    (s) => s.range_start_s <= req.start_s && req.end_s <= s.range_end_s,
  );
  if (covered) return fixture<StemsResponse>(stemsReadyFixture);
  fixturePolls.set(stemsQueuedFixture.job_id, 0); // each queued request starts a fresh "job"
  return fixture<StemsResponse>(stemsQueuedFixture);
}

function fixtureJob(id: string): Promise<Job> {
  if (id === jobDoneAnalyzeFixture.id) {
    // Analyze (import) job: "running" with rising progress for the first 2 polls after an import, then done.
    const n = (fixturePolls.get(id) ?? FIXTURE_RUNNING_POLLS) + 1;
    fixturePolls.set(id, n);
    return n <= FIXTURE_RUNNING_POLLS
      ? fixture<Job>({ ...jobDoneAnalyzeFixture, status: "running", progress: n / (FIXTURE_RUNNING_POLLS + 1), output: null })
      : fixture<Job>(jobDoneAnalyzeFixture);
  }
  if (id === jobDoneStemsFixture.id) {
    const n = (fixturePolls.get(id) ?? 0) + 1;
    fixturePolls.set(id, n);
    return fixture<Job>(n <= FIXTURE_RUNNING_POLLS ? jobRunningFixture : jobDoneStemsFixture);
  }
  return Promise.reject(new ApiError(404, "not_found", `job ${id} not found`));
}

export const api = {
  health: (): Promise<{ ok: boolean }> => (USE_FIXTURES ? fixture({ ok: true }, 0) : request("/health")),

  getChips: (): Promise<ChipsResponse> =>
    USE_FIXTURES ? fixture<ChipsResponse>(chipsFixture) : request("/chips"),

  search: (req: SearchRequest): Promise<SearchResponse> =>
    USE_FIXTURES ? fixtureSearch() : request("/search", json("POST", req)),

  getTrack: (trackId: string): Promise<TrackDetail> =>
    USE_FIXTURES
      ? fixture<TrackDetail>(trackDetailFixture)
      : request(`/tracks/${encodeURIComponent(trackId)}`),

  requestStems: (trackId: string, req: StemsRequest): Promise<StemsResponse> =>
    USE_FIXTURES
      ? fixtureStems(req)
      : request(`/tracks/${encodeURIComponent(trackId)}/stems`, json("POST", req)),

  getJob: (jobId: string): Promise<Job> =>
    USE_FIXTURES ? fixtureJob(jobId) : request(`/jobs/${encodeURIComponent(jobId)}`),

  createImport: (file: File, sessionId: string): Promise<ImportResponse> => {
    if (USE_FIXTURES) {
      fixturePolls.set(importFixture.job_id, 0); // each import starts a fresh analyze "job"
      return fixture<ImportResponse>(importFixture, 500);
    }
    const form = new FormData();
    form.append("file", file);
    form.append("session_id", sessionId);
    return request("/imports", { method: "POST", body: form }, UPLOAD_TIMEOUT_MS);
  },

  why: (req: WhyRequest): Promise<WhyResponse> =>
    USE_FIXTURES
      ? fixture<WhyResponse>({ ...whyFixture, window_id: req.window_id }, 400)
      : request("/why", json("POST", req)),

  postEvent: (req: EventRequest): Promise<void> =>
    USE_FIXTURES ? fixture<void>(undefined, 0) : request("/events", json("POST", req)),

  assist: (req: AssistRequest): Promise<AssistResponse> =>
    USE_FIXTURES ? fixture<AssistResponse>(assistFixture, 600) : request("/assist", json("POST", req)),
};

export type Api = typeof api;
