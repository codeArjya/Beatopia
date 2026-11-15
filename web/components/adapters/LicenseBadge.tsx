import { cn } from "cn";

import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { licenseUrl } from "@/lib/license";

/** License badge (links to the CC deed when known; tooltip = full attribution). Pair with <Attribution>. */
export function LicenseBadge({ license, attribution }: { license: string; attribution: string }) {
  const href = licenseUrl(license);
  const badge = (
    <Badge variant="outline" asChild className="rounded-[6px] border-input px-1.5 font-mono text-[11px] tracking-tight text-text-secondary outline-none hover:text-foreground focus-visible:ring-0 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ring [a&]:hover:bg-accent">
      {href ? (
        <a href={href} target="_blank" rel="noreferrer noopener" aria-label={`License ${license} (opens in new tab)`}>
          {license}
        </a>
      ) : (
        <span tabIndex={0} aria-label={`License ${license}`}>
          {license}
        </span>
      )}
    </Badge>
  );
  if (!attribution) return badge;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{badge}</TooltipTrigger>
      <TooltipContent className="max-w-xs">{attribution}</TooltipContent>
    </Tooltip>
  );
}

/** One-line muted attribution caption; AGENTS.md: the UI always shows license + attribution. */
export function Attribution({ text, className }: { text: string; className?: string }) {
  if (!text) return null;
  return (
    <p className={cn("truncate text-xs text-text-tertiary", className)} title={text}>
      {text}
    </p>
  );
}
