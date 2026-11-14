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

  it("a stems job runs, then finishes", async () => {
    const { stems } = await api.requestStems("jam_1532881", { start_s: 0, end_s: 10 });
    expect(stems).toHaveLength(4);
    const id = "5b1d6c1e-8a4f-4c55-9a51-2f0f6f3e7c11";
    expect((await api.getJob(id)).status).toBe("running");
    expect((await api.getJob(id)).status).toBe("running");
    expect((await api.getJob(id)).status).toBe("done");
  });

  it("unknown jobs reject with not_found", async () => {
    await expect(api.getJob("nope")).rejects.toBeInstanceOf(ApiError);
  });

  it("why echoes the requested window id", async () => {
    const res = await api.why({ window_id: "fs_482913:mix:5000" });
    expect(res.window_id).toBe("fs_482913:mix:5000");
  });
});
