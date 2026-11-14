import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api";

import { formatTime, formatWindow, resultsStatusText, searchErrorKind, searchErrorMessage, topTags } from "./results";

describe("searchErrorKind", () => {
  it("classifies ApiError codes", () => {
    expect(searchErrorKind(new ApiError(0, "network_error", "x"))).toBe("network");
    expect(searchErrorKind(new ApiError(429, "rate_limited", "x"))).toBe("retryable");
    expect(searchErrorKind(new ApiError(502, "upstream_error", "x"))).toBe("retryable");
    expect(searchErrorKind(new ApiError(422, "validation_error", "x"))).toBe("other");
    expect(searchErrorKind(new Error("boom"))).toBe("other");
    expect(searchErrorKind(undefined)).toBe("other");
  });

  it("has a readable message for each kind", () => {
    expect(searchErrorMessage(new ApiError(0, "network_error", "Failed to fetch"))).toMatch(/reach/);
    expect(searchErrorMessage(new ApiError(429, "rate_limited", "x"))).toMatch(/Too many/);
    expect(searchErrorMessage(new ApiError(400, "bad_request", "chips must be known"))).toBe("chips must be known");
    expect(searchErrorMessage(null)).toBe("Something went wrong.");
  });
});

describe("resultsStatusText", () => {
  const base = { pending: false, count: 8, refreshing: false, failed: false, fallback: false };
  it("counts results", () => {
    expect(resultsStatusText(base)).toBe("8 results");
    expect(resultsStatusText({ ...base, count: 1 })).toBe("1 result");
    expect(resultsStatusText({ ...base, count: 0, fallback: true })).toBe("0 results");
    expect(resultsStatusText({ ...base, count: 3, fallback: true, refreshing: true })).toBe(
      "3 results, expanded to Freesound, updating…",
    );
  });
  it("covers loading and failure without data", () => {
    expect(resultsStatusText({ ...base, pending: true, count: null })).toBe("Searching…");
    expect(resultsStatusText({ ...base, count: null, failed: true })).toBe("Search failed.");
    expect(resultsStatusText({ ...base, count: null })).toBe("");
  });
});

describe("topTags", () => {
  it("keeps the first 3 distinct non-empty tags", () => {
    expect(topTags(["rhodes", "soul", "melancholy", "dusty"])).toEqual(["rhodes", "soul", "melancholy"]);
    expect(topTags(["a", "a", " ", "b"])).toEqual(["a", "b"]);
    expect(topTags([])).toEqual([]);
  });
});

describe("formatWindow", () => {
  it("formats m:ss.s", () => {
    expect(formatTime(0)).toBe("0:00.0");
    expect(formatTime(5.333)).toBe("0:05.3");
    expect(formatTime(75.04)).toBe("1:15.0");
    expect(formatTime(59.96)).toBe("1:00.0");
    expect(formatTime(Number.NaN)).toBe("0:00.0");
    expect(formatWindow({ start_s: 5.333, end_s: 10.667 })).toBe("0:05.3–0:10.7");
  });
});
