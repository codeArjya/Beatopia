import { cn } from "cn";
import type { ComponentProps } from "react";

import { Input } from "@/components/ui/input";

/**
 * App text input. Feature code uses this, never components/ui/input. Pill-shaped on the `--secondary` surface with
 * a visible `--input` edge (3.6:1) that turns purple on focus.
 */
export function AppInput({ className, ...props }: ComponentProps<typeof Input>) {
  return (
    <Input
      className={cn(
        "h-10 rounded-full border-input bg-secondary px-4 text-[15px] shadow-none placeholder:text-text-tertiary md:text-[15px] dark:bg-secondary",
        "focus-visible:border-ring focus-visible:ring-0 focus-visible:outline-none",
        className,
      )}
      {...props}
    />
  );
}
