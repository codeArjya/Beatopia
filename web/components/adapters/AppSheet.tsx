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
            el.focus();
          }
        }}
      >
        <SheetHeader className="border-b">
          <SheetTitle>{title}</SheetTitle>
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
