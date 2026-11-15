import { afterEach, expect, it, vi } from "vitest";
import { ObjectUrls } from "./object-urls";

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });
it("releases each download URL once, on timeout or unmount, and clears timers", () => {
  vi.useFakeTimers();
  let index = 0;
  vi.spyOn(URL, "createObjectURL").mockImplementation(() => `blob:download-${++index}`);
  const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  const urls = new ObjectUrls();
  urls.create(new Blob()); vi.advanceTimersByTime(1000);
  expect(revoke.mock.calls).toEqual([["blob:download-1"]]);
  urls.create(new Blob()); urls.create(new Blob()); urls.dispose(); urls.dispose();
  vi.runAllTimers();
  expect(revoke.mock.calls).toEqual([["blob:download-1"], ["blob:download-2"], ["blob:download-3"]]);
  expect(vi.getTimerCount()).toBe(0);
});
