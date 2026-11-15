import { cn } from "cn";

/** Hardware-style readout (`.readout`: Geist Mono, tabular-nums) (BPM, key, bars). Null/undefined renders "—" with an accessible "unknown". */
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
    <span className={cn("readout inline-flex items-baseline gap-1 text-[13px]", className)}>
      <span className="sr-only">{label}: </span>
      {missing ? (
        <span className="text-text-tertiary" aria-label="unknown">
          —
        </span>
      ) : (
        <span>{shown}</span>
      )}
      {unit && !missing && <span className="text-[12px] text-text-tertiary">{unit}</span>}
    </span>
  );
}

function formatNumber(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, "");
}
