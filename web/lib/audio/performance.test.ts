import { expect, it } from "vitest";
import { runPerformanceChecks } from "./performance-checks";

it("profiles adding a pure op to a 16-bar stereo chain", async () => {
  const { fresh, cached } = await runPerformanceChecks((line) => console.info(line));
  // Avoid a machine-speed assertion in CI; sample equivalence/reuse is asserted by the harness.
  expect(Object.values(fresh).every(Number.isFinite)).toBe(true);
  expect(Object.values(cached).every(Number.isFinite)).toBe(true);
}, 60_000);
