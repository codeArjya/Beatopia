"use client";

import { useRef, type ReactNode } from "react";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

/**
 * Centered modal on the popover surface (shortcut help). Radix handles Esc and the focus trap. It is opened from
 * the keyboard without a trigger, so the element focused when it opened gets focus back on close.
 */
export function AppDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
}) {
  const opener = useRef<HTMLElement | null>(null);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="rounded-xl border-border bg-popover text-popover-foreground shadow-float data-[state=closed]:duration-150 data-[state=open]:duration-200 sm:max-w-md"
        onOpenAutoFocus={() => {
          opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        }}
        onCloseAutoFocus={(e) => {
          const el = opener.current;
          opener.current = null;
          if (el?.isConnected && el !== document.body) {
            e.preventDefault();
            el.focus();
          }
        }}
      >
        <DialogHeader>
          <DialogTitle className="text-lg leading-6 font-extrabold tracking-tight">{title}</DialogTitle>
          {description ? (
            <DialogDescription className="text-text-secondary">{description}</DialogDescription>
          ) : (
            <DialogDescription className="sr-only">Dialog</DialogDescription>
          )}
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  );
}
