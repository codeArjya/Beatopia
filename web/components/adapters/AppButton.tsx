import { cn } from "cn";
import type { ComponentProps } from "react";

import { Button } from "@/components/ui/button";

type ButtonProps = ComponentProps<typeof Button>;
type Variant = NonNullable<ButtonProps["variant"]>;

/**
 * Design-token skin per variant (docs/proposals/WS3-design-tokens.md): pill buttons, purple only for the one
 * main action (`default`), visible `--input` borders on outline buttons, hover = the `--accent` surface.
 * Merged after the shadcn classes, so these win.
 */
const SKIN: Record<Variant, string> = {
  default: "bg-primary font-semibold text-primary-foreground hover:bg-primary-hover",
  outline:
    "border-input bg-transparent text-foreground shadow-none hover:bg-accent hover:text-accent-foreground dark:border-input dark:bg-transparent dark:hover:bg-accent",
  ghost: "text-foreground hover:bg-accent hover:text-accent-foreground dark:hover:bg-accent",
  secondary: "bg-secondary text-secondary-foreground hover:bg-accent",
  destructive:
    "bg-destructive text-destructive-foreground hover:bg-destructive/90 dark:bg-destructive dark:hover:bg-destructive/90",
  link: "text-primary-strong",
};

const BASE =
  "rounded-full transition-[background-color,color,box-shadow,scale] duration-(--dur-hover) ease-(--ease-out) focus-visible:ring-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring active:scale-[0.97]";

/** App button. Feature code uses this, never components/ui/button, so the design pass restyles one place. */
export function AppButton({ className, variant = "default", ...props }: ButtonProps) {
  const v: Variant = variant ?? "default";
  return <Button variant={v} className={cn(BASE, SKIN[v], className)} {...props} />;
}
