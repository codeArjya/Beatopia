import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { contrast, readHexTokens } from "./contrast";

const css = readFileSync(path.join(__dirname, "../../app/globals.css"), "utf8");
const t = readHexTokens(css);

describe("contrast helper", () => {
  it("matches known WCAG values", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrast("#ffffff", "#ffffff")).toBeCloseTo(1, 5);
  });
});

describe("design tokens (app/globals.css) meet WCAG AA", () => {
  const CHIPS = ["chip-instrument", "chip-genre", "chip-mood", "chip-tempo", "chip-key"];

  it.each(CHIPS)("picked %s sticker: dark text on the hue is at least 4.5:1", (chip) => {
    expect(contrast(t["chip-picked-fg"], t[chip])).toBeGreaterThanOrEqual(4.5);
  });

  it("idle chip label is at least 4.5:1", () => {
    expect(contrast(t.foreground, t["chip-idle-bg"])).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t.foreground, t["chip-hover-bg"])).toBeGreaterThanOrEqual(4.5);
  });

  it.each([
    ["foreground", "background"],
    ["foreground", "card"],
    ["text-secondary", "card"],
    ["text-secondary", "popover"],
    ["text-tertiary", "background"],
    ["text-tertiary", "card"],
    ["text-tertiary", "secondary"],
    ["primary-strong", "background"],
    ["primary-strong", "card"],
    ["primary-foreground", "primary"],
    ["primary-foreground", "primary-hover"],
    ["destructive", "card"],
    ["destructive", "popover"],
    ["warning", "popover"],
    ["destructive-foreground", "destructive"],
  ])("%s on %s is at least 4.5:1", (fg, bg) => {
    expect(contrast(t[fg], t[bg])).toBeGreaterThanOrEqual(4.5);
  });

  it("control borders (--input) and the focus ring are at least 3:1 (non-text)", () => {
    expect(contrast(t.input, t.card)).toBeGreaterThanOrEqual(3);
    expect(contrast(t.input, t.secondary)).toBeGreaterThanOrEqual(3);
    expect(contrast(t.ring, t.background)).toBeGreaterThanOrEqual(3);
    expect(contrast(t.ring, t.card)).toBeGreaterThanOrEqual(3);
  });
});
