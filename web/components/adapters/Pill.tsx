import { cn } from "cn";
import { XIcon } from "lucide-react";
import { Slot } from "radix-ui";
import type { ComponentProps, CSSProperties } from "react";

/** Only a plain CSS custom property name is accepted as a color (ChipCategory.color, e.g. "--chip-genre"). */
export function pillColorVar(color: string | undefined): string {
  return color && /^--[a-z0-9-]+$/i.test(color) ? `var(${color})` : "var(--muted-foreground)";
}

type PillProps = ComponentProps<"span"> & {
  /** CSS variable name from ChipCategory.color. */
  color?: string;
  /** Tray chips use a lighter tint than stacked pills. */
  tone?: "solid" | "soft";
  selected?: boolean;
  /** Render the child element (e.g. a <button>) with pill styling instead of a <span>. No remove button then. */
  asChild?: boolean;
  onRemove?: () => void;
  removeLabel?: string;
};

/**
 * Category-colored chip. Forwards `ref` and any props (dnd-kit attributes/listeners) to the root element.
 * With `onRemove`, a separate remove <button> sits inside the pill (the root stays a span, so no nested buttons).
 */
export function Pill({
  color,
  tone = "solid",
  selected = false,
  asChild = false,
  onRemove,
  removeLabel,
  className,
  style,
  children,
  ...props
}: PillProps) {
  const Comp = asChild ? Slot.Root : "span";
  const tint = tone === "solid" || selected ? "22%" : "10%";
  return (
    <Comp
      data-slot="pill"
      data-selected={selected || undefined}
      style={{ "--pill": pillColorVar(color), "--pill-tint": tint, ...style } as CSSProperties}
      className={cn(
        "inline-flex h-7 max-w-full shrink-0 select-none items-center gap-1 rounded-full border px-2.5 text-sm font-medium whitespace-nowrap",
        "border-[color-mix(in_oklch,var(--pill)_70%,transparent)] bg-[color-mix(in_oklch,var(--pill)_var(--pill-tint),transparent)] text-foreground",
        "outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-[color-mix(in_oklch,var(--pill)_55%,transparent)]",
        asChild && "cursor-pointer hover:bg-[color-mix(in_oklch,var(--pill)_30%,transparent)]",
        selected && "border-[var(--pill)]",
        onRemove && "pr-1",
        className,
      )}
      {...props}
    >
      {asChild ? (
        children
      ) : (
        <>
          <span className="truncate">{children}</span>
          {onRemove && (
            <button
              type="button"
              onClick={onRemove}
              onPointerDown={(e) => e.stopPropagation()}
              aria-label={removeLabel ?? "Remove"}
              className="grid size-5 place-items-center rounded-full text-muted-foreground outline-none hover:bg-foreground/10 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
            >
              <XIcon className="size-3.5" aria-hidden />
            </button>
          )}
        </>
      )}
    </Comp>
  );
}
