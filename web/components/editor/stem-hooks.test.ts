import { afterEach, expect, it, vi } from "vitest";
import { MutationObserver, QueryClient, QueryObserver } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { Job, Stem } from "@/lib/types/api";
import { coveringStems } from "@/lib/audio/source-import";
import { stemJobOptions, stemPollInterval, stemRequestOptions } from "./stem-hooks";

afterEach(() => vi.restoreAllMocks());
const stem: Stem = { track_id: "hero", stem: "drums", url: "drums.wav", range_start_s: 5, range_end_s: 15, model: "htdemucs" };
const job: Job = { id: "job-1", kind: "stems", status: "queued", progress: 0 };

it("uses the typed client for immediately ready stems and preserves requested absolute range", async () => {
  const request = vi.spyOn(api, "requestStems").mockResolvedValue({ stems: [stem], job_id: null });
  const client = new QueryClient();
  try {
    const mutation = new MutationObserver(client, stemRequestOptions("hero", { start_s: 6, end_s: 9 }));
    const result = await mutation.mutate();
    expect(request).toHaveBeenCalledWith("hero", { start_s: 6, end_s: 9 });
    expect(coveringStems(result.stems ?? [], "hero", 6, 9)).toEqual([stem]);
  } finally { client.clear(); }
});

it("handles queued/running/done output, uses one-second polling, stops at terminal states and disables on close", async () => {
  vi.spyOn(api, "requestStems").mockResolvedValue({ job_id: job.id });
  const getJob = vi.spyOn(api, "getJob").mockResolvedValueOnce(job)
    .mockResolvedValueOnce({ ...job, status: "running", progress: 0.5 })
    .mockResolvedValueOnce({ ...job, status: "done", progress: 1, output: { stems: [stem] } });
  const client = new QueryClient();
  try {
    const mutation = new MutationObserver(client, stemRequestOptions("hero", { start_s: 6, end_s: 9 }));
    const response = await mutation.mutate();
    const options = stemJobOptions(response.job_id!, true);
    const first = await client.fetchQuery(options);
    expect(first.status).toBe("queued"); expect(stemPollInterval(first)).toBe(1000);
    const running = await client.fetchQuery(options);
    expect(running.progress).toBe(0.5); expect(stemPollInterval(running)).toBe(1000);
    const done = await client.fetchQuery(options);
    expect(stemPollInterval(done)).toBe(false);
    expect(done.output && "stems" in done.output && coveringStems(done.output.stems, "hero", 6, 9)).toEqual([stem]);
    const observer = new QueryObserver(client, stemJobOptions(job.id, false));
    const unsubscribe = observer.subscribe(() => {});
    expect(observer.getCurrentResult().fetchStatus).toBe("idle");
    expect(getJob).toHaveBeenCalledTimes(3);
    unsubscribe();
  } finally { client.clear(); }
});

it("surfaces request/poll/job errors, permits explicit retry and rejects unrelated jobs", async () => {
  const client = new QueryClient();
  const getJob = vi.spyOn(api, "getJob").mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ ...job, status: "error", error: "worker failed" })
    .mockResolvedValueOnce({ ...job, id: "wrong-job" });
  vi.spyOn(api, "requestStems").mockRejectedValueOnce(new Error("request failed")).mockResolvedValueOnce({ job_id: job.id });
  try {
    const mutation = new MutationObserver(client, stemRequestOptions("hero", { start_s: 6, end_s: 9 }));
    await expect(mutation.mutate()).rejects.toThrow("request failed");
    await expect(mutation.mutate()).resolves.toMatchObject({ job_id: job.id });
    await expect(client.fetchQuery(stemJobOptions(job.id, true))).rejects.toThrow("offline");
    expect(stemPollInterval(undefined, new Error("offline"))).toBe(false);
    expect(getJob).toHaveBeenCalledTimes(1);
    const failed = await client.fetchQuery(stemJobOptions(job.id, true));
    expect(failed.error).toBe("worker failed"); expect(stemPollInterval(failed)).toBe(false);
    await expect(client.fetchQuery(stemJobOptions(job.id, true))).rejects.toThrow("different stem job");
  } finally { client.clear(); }
});
