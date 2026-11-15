import { afterEach, describe, expect, it, vi } from "vitest";

vi.stubEnv("NEXT_PUBLIC_USE_FIXTURES", "0");
vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.test/");

describe("api client (live mode)", async () => {
  const { api, API_URL, ApiError, USE_FIXTURES } = await import("./client");

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses the API URL without a trailing slash", () => {
    expect(USE_FIXTURES).toBe(false);
    expect(API_URL).toBe("https://api.example.test");
  });

  it("sends search as JSON with a timeout signal", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ results: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await api.search({ text: "keys", chips: [], session_id: "s" });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://api.example.test/search");
    expect(init.method).toBe("POST");
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it("maps a timeout to code 'timeout'", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("timed out", "TimeoutError")));
    await expect(api.getChips()).rejects.toMatchObject({ status: 0, code: "timeout" });
  });

  it("maps a failed fetch (offline, CORS) to code 'network_error'", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.getChips()).rejects.toMatchObject({ status: 0, code: "network_error" });
  });

  it("reads the {error} body of a non-2xx response", async () => {
    const body = { error: { code: "rate_limited", message: "slow down" } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 429 })));
    const err = await api.getChips().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 429, code: "rate_limited", message: "slow down" });
  });

  it("falls back to http_error when the error body isn't JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>bad gateway</html>", { status: 502 })));
    await expect(api.getChips()).rejects.toMatchObject({ status: 502, code: "http_error" });
  });
});
