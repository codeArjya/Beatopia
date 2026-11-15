"use client";

import { KeyboardIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { AppButton, AppDialog } from "@/components/adapters";
import { SEARCH_INPUT_ID } from "@/components/shell/SkipLink";
import { isTypingTarget, shortcutAction, SHORTCUTS, stepIndex } from "@/lib/search/shortcuts";

const CARD = '[data-slot="app-card"]';

function cards(): HTMLElement[] {
  return [...document.querySelectorAll<HTMLElement>(`ol[aria-label="Results"] ${CARD}`)];
}

function focusedCard(): HTMLElement | null {
  return document.activeElement?.closest<HTMLElement>(CARD) ?? null;
}

/**
 * Search page shortcuts: `/` search box, `j`/`k` between result cards, `s` stems and `e` editor for the focused
 * card, `?` this help. Off while typing, with modifier keys, or while a sheet/dialog is open. Renders the help
 * dialog and a small "Shortcuts" button so the feature is discoverable without knowing `?`.
 */
export function SearchShortcuts() {
  const [helpOpen, setHelpOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      const action = shortcutAction({
        key: e.key,
        ctrlKey: e.ctrlKey,
        metaKey: e.metaKey,
        altKey: e.altKey,
        repeat: e.repeat,
        typing: isTypingTarget(document.activeElement),
        modalOpen: document.querySelector('[role="dialog"][data-state="open"]') !== null,
      });
      if (!action) return;

      if (action === "focusSearch") {
        const input = document.getElementById(SEARCH_INPUT_ID);
        if (!input) return;
        e.preventDefault(); // don't type the "/"
        input.focus();
      } else if (action === "help") {
        e.preventDefault();
        setHelpOpen(true);
      } else if (action === "nextCard" || action === "prevCard") {
        const list = cards();
        const current = focusedCard();
        const next = list[stepIndex(current ? list.indexOf(current) : -1, list.length, action === "nextCard" ? 1 : -1)];
        if (!next) return;
        e.preventDefault();
        next.focus();
        next.scrollIntoView({ block: "nearest" });
      } else {
        const card = focusedCard();
        const target = card?.querySelector<HTMLElement>(`[data-shortcut="${action === "openStems" ? "stems" : "editor"}"]`);
        if (!target) return;
        e.preventDefault();
        target.click();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <AppButton
        variant="ghost"
        size="xs"
        className="text-text-tertiary hover:text-foreground"
        aria-keyshortcuts="?"
        onClick={() => setHelpOpen(true)}
      >
        <KeyboardIcon aria-hidden />
        Shortcuts
      </AppButton>
      <AppDialog
        open={helpOpen}
        onOpenChange={setHelpOpen}
        title="Keyboard shortcuts"
        description="They work anywhere on the search page except while you type in a box."
      >
        <dl className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2.5 text-sm">
          {SHORTCUTS.map((s) => (
            <div key={s.keys} className="contents">
              <dt>
                <kbd className="readout inline-block min-w-8 rounded-[6px] bg-secondary px-2 py-0.5 text-center shadow-[inset_0_-2px_0_rgb(0_0_0/0.35)]">
                  {s.keys}
                </kbd>
              </dt>
              <dd className="text-text-secondary">{s.label}</dd>
            </div>
          ))}
        </dl>
      </AppDialog>
    </>
  );
}
