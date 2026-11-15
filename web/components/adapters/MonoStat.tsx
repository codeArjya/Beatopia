import { cn } from "cn";

/** Monospace tabular number (BPM, key, bars). Null/undefined renders "—" with an accessible "unknown". */
export function MonoStat({
  label,
  value,
  unit,
  className,
}: {
  label: string;
  value: string | number | null | undefined;
  unit?: string;
  className?: string;
}) {
  const missing = value === null || value === undefined || value === "";
  const shown = typeof value === "number" ? formatNumber(value) : value;
  return (
    <span className={cn("inline-flex items-baseline gap-1 font-mono text-xs tabular-nums", className)}>
      <span className="sr-only">{label}: </span>
      {missing ? (
        <span className="text-muted-foreground" aria-label="unknown">
          —
        </span>
      ) : (
        <span>{shown}</span>
      )}
      {unit && !missing && <span className="text-muted-foreground">{unit}</span>}
    </span>
  );
}

function formatNumber(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, "");
}
