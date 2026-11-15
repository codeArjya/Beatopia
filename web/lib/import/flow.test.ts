import { describe, expect, it, vi } from "vitest";

import doneAnalyze from "@fixtures/job_done_analyze.json";
import importRes from "@fixtures/import.json";
import { ApiError } from "@/lib/api/client";
import type { Job, TrackDetail } from "@/lib/types/api";

import { importEditorLink, importErrorMessage, importFlowState } from "./flow";

vi.stubEnv("NEXT_PUBLIC_USE_FIXTURES", "1");

const done = doneAnalyze as Job;
const detail = (done.output as { track: TrackDetail }).track;
const uploaded = { status: "success" as const, error: null, data: importRes };
const job = (j: Partial<Job> | undefined) => ({ data: j ? ({ ...done, ...j } as Job) : undefined, error: null });

describe("importFlowState", () => {
  it("idle → uploading → upload error", () => {
    expect(importFlowState({ status: "idle", error: null, data: undefined }, job(undefined)).status).toBe("idle");
    expect(importFlowState({ status: "pending", error: null, data: undefined }, job(undefined))).toMatchObject({ status: "uploading", progress: null });
    const failed = importFlowState({ status: "error", error: new ApiError(413, "upload_too_large", "x"), data: undefined }, job(undefined));
    expect(failed).toMatchObject({ status: "error", failedAt: "upload" });
    expect(failed.error).toMatch(/25 MB/);
  });

  it("uploaded: queued until the first poll, then analyzing with progress, then done with the track", () => {
    expect(importFlowState(uploaded, job(undefined))).toMatchObject({ status: "queued", progress: 0 });
    expect(importFlowState(uploaded, job({ status: "queued", progress: 0, output: null })).status).toBe("queued");
    expect(importFlowState(uploaded, job({ status: "running", progress: 0.4, output: null }))).toMatchObject({ status: "analyzing", progress: 0.4 });
    const ok = importFlowState(uploaded, job({}));
    expect(ok).toMatchObject({ status: "done", progress: 1 });
    expect(ok.track?.track).toMatchObject({ bpm: 90, key: "A minor" });
  });

  it("analysis failures: job error, done without output, lost poll", () => {
    expect(importFlowState(uploaded, job({ status: "error", error: "could not decode", output: null }))).toMatchObject({
      status: "error",
      error: "could not decode",
      failedAt: "analyze",
    });
    expect(importFlowState(uploaded, job({ output: null })).failedAt).toBe("analyze");
    expect(importFlowState(uploaded, { data: undefined, error: new Error("404") })).toMatchObject({ status: "error", failedAt: "analyze" });
    // A failed poll after we already have a job keeps showing progress (polling continues).
    expect(importFlowState(uploaded, { data: { ...done, status: "running", output: null }, error: new Error("blip") }).status).toBe("analyzing");
  });
});

describe("importEditorLink", () => {
  it("uses the most loopable window, earliest on ties", () => {
    expect(importEditorLink(detail)).toEqual({ track: "imp_3f9a1c2e", start: 0, end: 10, stem: "mix" });
    const w = detail.windows;
    const better = { ...detail, windows: [w[0], { ...w[1], loopability: 0.95 }] };
    expect(importEditorLink(better)).toMatchObject({ start: 5, end: 15 });
  });

  it("falls back to 8 bars from 0 (cut to the track), or 16 s with no tempo", () => {
    const none = { ...detail, windows: [] };
    expect(importEditorLink(none)).toMatchObject({ start: 0, end: 16 }); // 8 bars at 90 BPM = 21.33 s > 16 s duration
    const long = { ...none, track: { ...none.track, duration_s: 60 } };
    expect(importEditorLink(long).end).toBeCloseTo(21.333, 2);
    expect(importEditorLink({ ...long, track: { ...long.track, bpm: null } }).end).toBe(16);
    expect(importEditorLink({ ...none, track: { ...none.track, duration_s: 4 } }).end).toBe(4);
  });
});

describe("importErrorMessage", () => {
  it("maps codes to plain text and passes the server's format message through", () => {
    expect(importErrorMessage(new ApiError(415, "unsupported_format", "the file is named .mp3 but looks like wav"))).toMatch(/named \.mp3/);
    expect(importErrorMessage(new ApiError(0, "network_error", "Failed to fetch"))).toMatch(/Couldn't reach/);
    expect(importErrorMessage(new Error("?"))).toBe("Import failed. Try again.");
  });
});
