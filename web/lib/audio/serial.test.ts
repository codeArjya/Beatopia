import { expect, it } from "vitest";
import { createSerialQueue } from "./serial";

it("serializes jobs across awaits and releases a failed job without swallowing its error", async () => {
  const enqueue = createSerialQueue();
  const events: string[] = [];
  let release!: () => void;
  const blocked = new Promise<void>((resolve) => { release = resolve; });
  const first = enqueue(async () => { events.push("first start"); await blocked; events.push("first end"); return 1; });
  const second = enqueue(async () => { events.push("second"); throw new Error("render failed"); });
  const rejected = expect(second).rejects.toThrow("render failed");
  const third = enqueue(async () => { events.push("third"); return 3; });
  await Promise.resolve();
  expect(events).toEqual(["first start"]);
  release();
  expect(await first).toBe(1);
  await rejected;
  expect(await third).toBe(3);
  expect(events).toEqual(["first start", "first end", "second", "third"]);
});
