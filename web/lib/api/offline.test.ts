import { describe, expect, it } from "vitest";

import { OFFLINE_KEY, offlineToggleHref, resolveOffline } from "./offline";

function memoryStore(init: Record<string, string> = {}) {
  const m = new Map(Object.entries(init));
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
    map: m,
  };
}

describe("resolveOffline", () => {
  it("?offline=1 turns it on and remembers it", () => {
    const s = memoryStore();
    expect(resolveOffline("?offline=1&chips=a", s)).toBe(true);
    expect(s.map.get(OFFLINE_KEY)).toBe("1");
    expect(resolveOffline("?chips=a", s)).toBe(true); // a later load without the flag
  });

  it("?offline=0 turns it off and forgets it", () => {
    const s = memoryStore({ [OFFLINE_KEY]: "1" });
    expect(resolveOffline("?offline=0", s)).toBe(false);
    expect(s.map.has(OFFLINE_KEY)).toBe(false);
    expect(resolveOffline("", s)).toBe(false);
  });

  it("is off by default, and other values don't count", () => {
    expect(resolveOffline("", memoryStore())).toBe(false);
    expect(resolveOffline("?offline=yes", memoryStore())).toBe(false);
    expect(resolveOffline("?offline=1", null)).toBe(true);
  });

  it("falls back to the URL flag when storage throws", () => {
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    };
    expect(resolveOffline("?offline=1", broken)).toBe(true);
    expect(resolveOffline("", broken)).toBe(false);
  });
});

describe("offlineToggleHref", () => {
  it("keeps the path, other params and hash", () => {
    expect(offlineToggleHref("http://x.test/?chips=a,b#r", false)).toBe("/?chips=a%2Cb&offline=0#r");
    expect(offlineToggleHref("http://x.test/import?offline=0", true)).toBe("/import?offline=1");
  });
});
