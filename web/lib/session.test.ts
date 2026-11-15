import { afterEach, describe, expect, it, vi } from "vitest";

import { getSessionId } from "./session";

describe("getSessionId", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("is stable across calls without a window (SSR / node)", () => {
    expect(getSessionId()).toBe(getSessionId());
  });

  it("persists to and reads from localStorage", () => {
    const store = new Map<string, string>();
    vi.stubGlobal("window", {
      localStorage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) },
    });
    const id = getSessionId();
    expect(store.get("session_id")).toBe(id);
    store.set("session_id", "from-storage");
    expect(getSessionId()).toBe("from-storage");
  });

  it("falls back to memory when storage throws", () => {
    vi.stubGlobal("window", {
      localStorage: {
        getItem: () => {
          throw new Error("blocked");
        },
      },
    });
    const a = getSessionId();
    expect(a).toBeTruthy();
    expect(getSessionId()).toBe(a);
  });
});
