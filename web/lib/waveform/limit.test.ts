import { describe, expect, it } from "vitest";

import { createLimiter, LruCache } from "./limit";

function deferred<T = void>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe("createLimiter", () => {
  it("runs at most `max` tasks at once, in FIFO order", async () => {
    const limit = createLimiter(2);
    const gates = [deferred(), deferred(), deferred(), deferred()];
    const started: number[] = [];
    const done = gates.map((g, i) =>
      limit(async () => {
        started.push(i);
        await g.promise;
        return i;
      }),
    );
    await flush();
    expect(started).toEqual([0, 1]);

    gates[1].resolve();
    await flush();
    expect(started).toEqual([0, 1, 2]);

    gates[0].reject(new Error("boom")); // a failure frees its slot too
    await expect(done[0]).rejects.toThrow("boom");
    await flush();
    expect(started).toEqual([0, 1, 2, 3]);

    gates[2].resolve();
    gates[3].resolve();
    await expect(Promise.all(done.slice(1))).resolves.toEqual([1, 2, 3]);
  });
});

describe("LruCache", () => {
  it("evicts the least recently used entry", () => {
    const c = new LruCache<string, number>(2);
    c.set("a", 1);
    c.set("b", 2);
    expect(c.get("a")).toBe(1); // a is now the most recent
    c.set("c", 3);
    expect(c.keys()).toEqual(["a", "c"]);
    expect(c.get("b")).toBeUndefined();
  });

  it("deletes only the given value when `only` is passed", () => {
    const c = new LruCache<string, number>(2);
    c.set("a", 1);
    c.delete("a", 2);
    expect(c.get("a")).toBe(1);
    c.delete("a", 1);
    expect(c.get("a")).toBeUndefined();
  });
});
