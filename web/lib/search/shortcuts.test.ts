import { describe, expect, it } from "vitest";

import { shortcutAction, stepIndex } from "./shortcuts";

describe("shortcutAction", () => {
  it.each([
    ["/", "focusSearch"],
    ["j", "nextCard"],
    ["J", "nextCard"],
    ["k", "prevCard"],
    ["s", "openStems"],
    ["e", "openEditor"],
    ["?", "help"],
  ])("%s → %s", (key, action) => expect(shortcutAction({ key })).toBe(action));

  it("ignores other keys", () => {
    expect(shortcutAction({ key: "x" })).toBeNull();
    expect(shortcutAction({ key: "Enter" })).toBeNull();
    expect(shortcutAction({ key: " " })).toBeNull();
  });

  it("never fires while typing, with modifiers, or under a modal", () => {
    expect(shortcutAction({ key: "s", typing: true })).toBeNull();
    expect(shortcutAction({ key: "/", typing: true })).toBeNull();
    expect(shortcutAction({ key: "s", metaKey: true })).toBeNull();
    expect(shortcutAction({ key: "e", ctrlKey: true })).toBeNull();
    expect(shortcutAction({ key: "j", altKey: true })).toBeNull();
    expect(shortcutAction({ key: "s", modalOpen: true })).toBeNull();
  });

  it("auto-repeat moves between cards but doesn't re-open things", () => {
    expect(shortcutAction({ key: "j", repeat: true })).toBe("nextCard");
    expect(shortcutAction({ key: "s", repeat: true })).toBeNull();
    expect(shortcutAction({ key: "?", repeat: true })).toBeNull();
  });
});

describe("stepIndex", () => {
  it("starts at the ends when nothing is focused", () => {
    expect(stepIndex(-1, 8, 1)).toBe(0);
    expect(stepIndex(-1, 8, -1)).toBe(7);
  });
  it("moves and clamps", () => {
    expect(stepIndex(3, 8, 1)).toBe(4);
    expect(stepIndex(3, 8, -1)).toBe(2);
    expect(stepIndex(7, 8, 1)).toBe(7);
    expect(stepIndex(0, 8, -1)).toBe(0);
  });
  it("is -1 with no cards", () => expect(stepIndex(0, 0, 1)).toBe(-1));
});
