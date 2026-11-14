import { QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import doneAnalyze from "@fixtures/job_done_analyze.json";
import doneStems from "@fixtures/job_done_stems.json";
import running from "@fixtures/job_running.json";
import type { Job } from "@/lib/types/api";

vi.stubEnv("NEXT_PUBLIC_USE_FIXTURES", "1");

describe("lib/api query factories (fixture mode)", async () => {
  const q = await import("./queries");
  const { keys } = await import("./keys");
  const client = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

  afterEach(() => vi.unstubAllGlobals());

  it("chips → 5 categories", async () => {
    const res = await client().fetchQuery(q.chipsQuery());
    expect(res.categories).toHaveLength(5);
  });

  it("search → 8 results", async () => {
    const res = await client().fetchQuery(q.searchQuery({ text: "dusty keys", chips: ["genre.soul"], limit: 8 }));
    expect(res.results).toHaveLength(8);
  });

  it("search with null params is idle (skipToken)", () => {
    const opts = q.searchQuery(null);
    expect(opts.queryKey).toEqual(["search", null]);
    expect(typeof opts.queryFn).not.toBe("function");
  });

  it("?fixture=empty and ?fixture=fallback serve the variant fixtures", async () => {
    const params = { text: "x", chips: [], limit: 8 };
    vi.stubGlobal("window", { location: { search: "?fixture=empty" } });
    const empty = await client().fetchQuery(q.searchQuery(params));
    expect(empty.results).toHaveLength(0);
    expect(empty.fallback_used).toBe(true);
    vi.stubGlobal("window", { location: { search: "?q=x&fixture=fallback" } });
    const fb = await client().fetchQuery(q.searchQuery(params));
    expect(fb.fallback_used).toBe(true);
    expect(fb.results.some((r) => r.track.bpm === null)).toBe(true);
  });

  it("track and stems queries resolve", async () => {
    const qc = client();
    const track = await qc.fetchQuery(q.trackQuery("jam_1532881"));
    expect(track.beat_times.length).toBeGreaterThan(0);
    const ready = await qc.fetchQuery(q.stemsQuery("jam_1532881", { start_s: 0, end_s: 10.667 }));
    expect(ready.stems).toHaveLength(4);
    expect(q.stemsQuery("x", null).queryFn).not.toBeTypeOf("function");
    expect(q.stemsQuery("x", { start_s: 0, end_s: 4 }).retry).toBe(false);
  });

  it("job polling: 1000 ms while queued/running, false once done or failed", () => {
    expect(q.jobPollInterval(undefined)).toBe(1000);
    expect(q.jobPollInterval(running as Job)).toBe(1000);
    expect(q.jobPollInterval(doneStems as Job)).toBe(false);
    expect(q.jobPollInterval({ ...(running as Job), status: "error" })).toBe(false);
  });

  it("job output narrows to stems or track", () => {
    expect(q.jobStems(doneStems as Job)).toHaveLength(4);
    expect(q.jobTrack(doneStems as Job)).toBeNull();
    expect(q.jobTrack(doneAnalyze as Job)?.track.id).toMatch(/^imp_/);
    expect(q.jobStems(doneAnalyze as Job)).toBeNull();
    expect(q.jobStems(running as Job)).toBeNull();
  });

  it("why: a cached note is served without a request; otherwise it fetches", async () => {
    const qc = client();
    const cached = q.whyQuery("w1", "Loops cleanly on the downbeat.");
    expect(cached.initialData).toEqual({ window_id: "w1", note: "Loops cleanly on the downbeat." });
    const fetched = await qc.fetchQuery(q.whyQuery("fs_482913:mix:5000", null));
    expect(fetched.window_id).toBe("fs_482913:mix:5000");
  });

  it("session id is not part of any key", () => {
    expect(JSON.stringify(keys.search({ text: "a", chips: [], limit: 8 }))).not.toContain("session");
  });
});
