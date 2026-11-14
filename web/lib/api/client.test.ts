import { describe, expect, it, vi } from "vitest";

vi.stubEnv("NEXT_PUBLIC_USE_FIXTURES", "1");

describe("api client (fixture mode)", async () => {
  const { api, ApiError, USE_FIXTURES } = await import("./client");

  it("is in fixture mode", () => {
    expect(USE_FIXTURES).toBe(true);
  });

  it("search returns the 8 fixture results", async () => {
    const res = await api.search({ text: "dusty soul keys", chips: [], session_id: "test" });
    expect(res.results).toHaveLength(8);
    expect(res.results[0].audio_url).toMatch(/^\/fixtures\/audio\//);
  });

  it("chips cover all five categories", async () => {
    const res = await api.getChips();
    expect(res.categories.map((c) => c.id)).toEqual(["instrument", "genre", "mood", "tempo", "key"]);
  });

  it("stems inside the fixture stems' range are ready right away", async () => {
    const res = await api.requestStems("jam_1532881", { start_s: 2, end_s: 12 });
    expect(res.job_id).toBeNull();
    expect(res.stems).toHaveLength(4);
  });

  it("stems outside the fixture range are queued; the job runs for 2 polls, then is done", async () => {
    const res = await api.requestStems("jam_1532881", { start_s: 10, end_s: 40 });
    expect(res.stems).toBeNull();
    expect(res.job_id).toBe("5b1d6c1e-8a4f-4c55-9a51-2f0f6f3e7c11");
    const id = res.job_id as string;
    expect((await api.getJob(id)).status).toBe("running");
    expect((await api.getJob(id)).status).toBe("running");
    const done = await api.getJob(id);
    expect(done.status).toBe("done");
    expect(done.output).toHaveProperty("stems");
    // a new queued request starts the mock job over
    await api.requestStems("jam_1532881", { start_s: 10, end_s: 40 });
    expect((await api.getJob(id)).status).toBe("running");
  });

  it("unknown jobs reject with not_found", async () => {
    await expect(api.getJob("nope")).rejects.toBeInstanceOf(ApiError);
  });

  it("why echoes the requested window id", async () => {
    const res = await api.why({ window_id: "fs_482913:mix:5000" });
    expect(res.window_id).toBe("fs_482913:mix:5000");
  });
});
