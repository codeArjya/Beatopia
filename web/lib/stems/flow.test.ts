import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import running from "@fixtures/job_running.json";
import ready from "@fixtures/stems_ready.json";
import type { Job, Stem, StemsResponse } from "@/lib/types/api";

import { clampStemsRange, sortStems, stemPreviewItem, stemsFlowState } from "./flow";

vi.stubEnv("NEXT_PUBLIC_USE_FIXTURES", "1");

const ok = <T,>(data: T | undefined) => ({ data, error: null });
const none = ok<Job>(undefined);

describe("clampStemsRange", () => {
  it("keeps ranges up to 60 s and clamps longer ones", () => {
    expect(clampStemsRange(0, 10.667)).toEqual({ start_s: 0, end_s: 10.667 });
    expect(clampStemsRange(30, 90)).toEqual({ start_s: 30, end_s: 90 });
    expect(clampStemsRange(30, 120)).toEqual({ start_s: 30, end_s: 90 });
    expect(clampStemsRange(-1, 5)).toEqual({ start_s: 0, end_s: 5 });
  });
});

describe("stemsFlowState", () => {
  it("idle until requested, then requesting", () => {
    expect(stemsFlowState(false, ok<StemsResponse>(undefined), none).status).toBe("idle");
    expect(stemsFlowState(true, ok<StemsResponse>(undefined), none).status).toBe("requesting");
  });

  it("ready at once when the response carries stems", () => {
    const s = stemsFlowState(true, ok(ready as StemsResponse), none);
    expect(s).toMatchObject({ status: "ready", progress: 1 });
    expect(s.stems).toHaveLength(4);
  });

  it("job path: queued → running with progress → error with the job's message", () => {
    const queued = ok<StemsResponse>({ job_id: "j", stems: null });
    expect(stemsFlowState(true, queued, none).status).toBe("queued");
    expect(stemsFlowState(true, queued, ok(running as Job))).toMatchObject({ status: "running", progress: 0.45 });
    const failed = stemsFlowState(true, queued, ok({ ...(running as Job), status: "error", error: "demucs OOM" }));
    expect(failed).toMatchObject({ status: "error", error: "demucs OOM" });
  });

  it("a request error is an error state", () => {
    const s = stemsFlowState(true, { data: undefined, error: new Error("boom") }, none);
    expect(s).toMatchObject({ status: "error", error: "boom" });
  });

  it("fixture mode: 0–10.667 ready at once; past 16 s queued → running (2 polls) → done", async () => {
    const q = await import("@/lib/api/queries");
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const hero = await qc.fetchQuery(q.stemsQuery("jam_1532881", clampStemsRange(0, 10.667)));
    expect(stemsFlowState(true, ok(hero), none).status).toBe("ready");

    const res = await qc.fetchQuery(q.stemsQuery("jam_1532881", clampStemsRange(10.667, 21.333)));
    expect(stemsFlowState(true, ok(res), none).status).toBe("queued");
    const statuses: string[] = [];
    for (let i = 0; i < 3; i++) {
      const job = await qc.fetchQuery({ ...q.jobQuery(res.job_id!), staleTime: 0 });
      statuses.push(stemsFlowState(true, ok(res), ok(job)).status);
    }
    expect(statuses).toEqual(["running", "running", "ready"]);
  });
});

describe("stemPreviewItem (offset math)", () => {
  const stem = (range_start_s: number, range_end_s: number): Stem => ({
    track_id: "t",
    stem: "drums",
    url: "/s.mp3",
    range_start_s,
    range_end_s,
    model: "htdemucs",
  });

  it("full-length hero stem: file time = track time", () => {
    expect(stemPreviewItem(stem(0, 180), 5.333, 16)).toMatchObject({ start: 5.333, end: 16 });
  });

  it("range stem: shifts by range_start_s", () => {
    const it = stemPreviewItem(stem(10, 30), 12, 20);
    expect(it.start).toBeCloseTo(2);
    expect(it.end).toBeCloseTo(10);
  });

  it("clamps to what the file covers", () => {
    expect(stemPreviewItem(stem(10, 20), 8, 25)).toMatchObject({ start: 0, end: 10 });
  });

  it("ids differ per stem and per window", () => {
    const a = stemPreviewItem(stem(0, 16), 0, 8).id;
    expect(stemPreviewItem({ ...stem(0, 16), stem: "bass" }, 0, 8).id).not.toBe(a);
    expect(stemPreviewItem(stem(0, 16), 8, 16).id).not.toBe(a);
  });
});

describe("sortStems", () => {
  it("drums, bass, vocals, then the rest", () => {
    const s = (name: Stem["stem"]): Stem => ({ ...(ready.stems[0] as Stem), stem: name });
    expect(sortStems([s("other"), s("vocals"), s("bass"), s("drums")]).map((x) => x.stem)).toEqual([
      "drums",
      "bass",
      "vocals",
      "other",
    ]);
  });
});
