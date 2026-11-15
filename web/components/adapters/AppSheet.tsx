"use client";

import { useRef, type ReactNode } from "react";

import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";

type AppSheetProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  side?: "right" | "left" | "bottom";
  children: ReactNode;
};

/**
 * Side drawer (stems). Radix handles the focus trap and Esc. It only returns focus to a `DialogTrigger`, and this
 * sheet is controlled without one, so the element focused when it opened is remembered and refocused on close.
 */
export function AppSheet({ open, onOpenChange, title, description, side = "right", children }: AppSheetProps) {
  const opener = useRef<HTMLElement | null>(null);
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side={side}
        className="flex w-full flex-col gap-0 sm:max-w-md"
        // Runs before Radix moves focus into the sheet, so activeElement is still the opener.
        onOpenAutoFocus={() => {
          opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        }}
        onCloseAutoFocus={(e) => {
          const el = opener.current;
          opener.current = null;
          if (el?.isConnected) {
            e.preventDefault();
            restoreFocus(el);
          }
        }}
      >
        <SheetHeader className="border-b">
          <SheetTitle className="line-clamp-2 break-words pr-6">{title}</SheetTitle>
          {description ? (
            <SheetDescription>{description}</SheetDescription>
          ) : (
            <SheetDescription className="sr-only">Drawer</SheetDescription>
          )}
        </SheetHeader>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
      </SheetContent>
    </Sheet>
  );
}

/** Give up waiting for a disabled opener after this long. */
const RESTORE_WAIT_MS = 15_000;

/**
 * Focus the opener. A disabled button can't take focus: the editor disables its Stems button while it decodes
 * the stem picked in this sheet. So wait until it's enabled again, then focus it, unless the user has already
 * moved focus somewhere else.
 */
function restoreFocus(el: HTMLElement) {
  const disabled = () => el.matches(":disabled");
  if (!disabled()) {
    el.focus();
    return;
  }
  const lost = () => document.activeElement === null || document.activeElement === document.body;
  const done = () => {
    observer.disconnect();
    clearTimeout(timer);
  };
  const observer = new MutationObserver(() => {
    if (!el.isConnected || !lost()) return done();
    if (!disabled()) {
      done();
      el.focus();
    }
  });
  observer.observe(el, { attributes: true, attributeFilter: ["disabled"] });
  const timer = setTimeout(done, RESTORE_WAIT_MS);
}
