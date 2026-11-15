import { cn } from "cn";
import type { ComponentProps } from "react";

/**
 * Card surface as an <article> (result cards are focusable articles labelled by their title). Quiet by default:
 * a hairline on `--card`, a slightly lighter edge on hover, the purple focus outline from the tokens.
 */
export function AppCard({ className, ...props }: ComponentProps<"article">) {
  return (
    <article
      data-slot="app-card"
      className={cn(
        "flex flex-col gap-3 rounded-lg border border-border bg-card p-4 text-card-foreground outline-none",
        "transition-[border-color,background-color] duration-(--dur-hover) ease-(--ease-out) hover:border-accent",
        "focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ring",
        className,
      )}
      {...props}
    />
  );
}
