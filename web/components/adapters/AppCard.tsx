import { cn } from "cn";
import type { ComponentProps } from "react";

/** Card surface as an <article> (result cards are focusable articles labelled by their title). */
export function AppCard({ className, ...props }: ComponentProps<"article">) {
  return (
    <article
      data-slot="app-card"
      className={cn(
        "flex flex-col gap-3 rounded-xl border bg-card p-4 text-card-foreground shadow-sm outline-none transition-colors",
        "focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:border-ring",
        className,
      )}
      {...props}
    />
  );
}
