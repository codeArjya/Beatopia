"use client";

import { cn } from "cn";
import { LoaderCircleIcon, PlayIcon, SquareIcon, TriangleAlertIcon } from "lucide-react";

import { AppButton } from "@/components/adapters";
import { usePreviewPlayer, usePreviewStatus, type PreviewItem } from "@/lib/preview/PreviewProvider";

/** Round play/stop toggle for one preview item on the shared player. `title` names the item for screen readers. */
export function PlayButton({ item, title, className }: { item: PreviewItem; title: string; className?: string }) {
  const player = usePreviewPlayer();
  const status = usePreviewStatus(item.id);
  const active = status === "playing" || status === "loading";
  const Icon =
    status === "playing" ? SquareIcon : status === "loading" ? LoaderCircleIcon : status === "error" ? TriangleAlertIcon : PlayIcon;
  const label =
    status === "error" ? `Preview failed, retry ${title}` : active ? `Stop preview of ${title}` : `Play preview of ${title}`;

  return (
    <AppButton
      size="icon"
      // The accent's main job (design tokens): play is always the purple round button; an error turns it outline-red.
      variant={status === "error" ? "outline" : "default"}
      className={cn(
        "shrink-0 rounded-full hover:scale-105",
        active && "bg-primary-hover",
        status === "error" && "border-destructive text-destructive hover:text-destructive",
        className,
      )}
      aria-label={label}
      aria-pressed={active}
      title={status === "error" ? "Couldn't play this preview. Click to retry." : undefined}
      onClick={() => player.toggle(item)}
    >
      <Icon className={cn("size-4", status === "loading" && "animate-spin", status !== "loading" && status !== "error" && "fill-current")} aria-hidden />
    </AppButton>
  );
}
