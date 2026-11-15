import { cn } from "cn";
import { XIcon } from "lucide-react";
import { Slot } from "radix-ui";
import type { ComponentProps, CSSProperties } from "react";

/** Only a plain CSS custom property name is accepted as a color (ChipCategory.color, e.g. "--chip-genre"). */
export function pillColorVar(color: string | undefined): string {
  return color && /^--[a-z0-9-]+$/i.test(color) ? `var(${color})` : "var(--chip-key)";
}

type PillProps = ComponentProps<"span"> & {
  /** CSS variable name from ChipCategory.color. */
  color?: string;
  /**
   * `solid`: a stacked chip (search bar, drag overlay), always a sticker that snaps in on mount.
   * `soft`: a tray chip, a plain gray label until `selected`.
   */
  tone?: "solid" | "soft";
  selected?: boolean;
  /** Render the child element (e.g. a <button>) with pill styling instead of a <span>. No remove button then. */
  asChild?: boolean;
  onRemove?: () => void;
  removeLabel?: string;
};

/**
 * Category chip as a "crate sticker" (the `.chip` rules in app/globals.css). Forwards `ref` and any props
 * (dnd-kit attributes/listeners) to the root element. With `onRemove`, a separate remove <button> sits inside
 * the pill (the root stays a span, so no nested buttons).
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
  const sticker = tone === "solid" || selected;
  return (
    <Comp
      data-slot="pill"
      data-tone={tone}
      data-selected={selected || undefined}
      data-sticker={sticker || undefined}
      style={{ "--chip": pillColorVar(color), ...style } as CSSProperties}
      className={cn(
        "chip shrink-0 outline-none",
        tone === "soft" && "h-8 px-2.5 text-[13px] [@media(pointer:coarse)]:h-11",
        tone === "solid" && "motion-safe:animate-chip-snap",
        asChild && "cursor-pointer",
        onRemove && "pr-1",
        className,
      )}
      {...props}
    >
      {asChild ? (
        children
      ) : (
        <>
          <span className="min-w-0 truncate">{children}</span>
          {onRemove && (
            <button
              type="button"
              onClick={onRemove}
              onPointerDown={(e) => e.stopPropagation()}
              aria-label={removeLabel ?? "Remove"}
              className="grid size-6 shrink-0 place-items-center rounded-[4px] text-current opacity-70 outline-none transition-[opacity,background-color] hover:bg-black/15 hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring"
            >
              <XIcon className="size-3.5" aria-hidden strokeWidth={2.5} />
            </button>
          )}
        </>
      )}
    </Comp>
  );
}
