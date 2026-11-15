// Search page keyboard shortcuts (T9.4). Pure: key → action, plus the card index arithmetic.

export type ShortcutAction = "focusSearch" | "nextCard" | "prevCard" | "openStems" | "openEditor" | "help";

export const SHORTCUTS: ReadonlyArray<{ keys: string; label: string }> = [
  { keys: "/", label: "Focus the search box" },
  { keys: "j / k", label: "Next / previous result" },
  { keys: "Space", label: "Play or stop the focused result" },
  { keys: "s", label: "Open stems of the focused result" },
  { keys: "e", label: "Open the focused result in the editor" },
  { keys: "?", label: "Show these shortcuts" },
  { keys: "Esc", label: "Close a drawer or dialog" },
];

export type KeyInput = {
  key: string;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
  /** Focus is in a text field, select or contenteditable: letters belong to it. */
  typing?: boolean;
  /** A modal (stems sheet, help) is open: it owns the keyboard. */
  modalOpen?: boolean;
  /** Key auto-repeat. */
  repeat?: boolean;
};

const MAP: Record<string, ShortcutAction> = {
  "/": "focusSearch",
  j: "nextCard",
  k: "prevCard",
  s: "openStems",
  e: "openEditor",
  "?": "help",
};

/** The action for a keydown, or null when the key isn't a shortcut here. Shift is fine ("?" needs it). */
export function shortcutAction(e: KeyInput): ShortcutAction | null {
  if (e.ctrlKey || e.metaKey || e.altKey || e.typing || e.modalOpen) return null;
  const action = MAP[e.key.length === 1 ? e.key.toLowerCase() : e.key] ?? null;
  if (action && e.repeat && action !== "nextCard" && action !== "prevCard") return null;
  return action;
}

/** Next card index for j (+1) / k (−1), clamped. With no focused card (-1), j goes to the first and k to the last. */
export function stepIndex(current: number, count: number, dir: 1 | -1): number {
  if (count <= 0) return -1;
  if (current < 0) return dir === 1 ? 0 : count - 1;
  return Math.min(count - 1, Math.max(0, current + dir));
}

/** True for elements that take typed text. */
export function isTypingTarget(el: Element | null): boolean {
  if (!el) return false;
  const tag = el.tagName;
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (tag === "INPUT") {
    const type = (el as HTMLInputElement).type;
    return !["button", "checkbox", "radio", "range", "submit", "reset", "file", "color"].includes(type);
  }
  return (el as HTMLElement).isContentEditable === true;
}
