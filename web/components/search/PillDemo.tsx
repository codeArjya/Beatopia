"use client";

// TEMPORARY (T1.3 acceptance): one tray chip + one stacked pill per category. Removed when ChipTray lands (T2.2).
import { Attribution, LicenseBadge, MonoStat, Pill } from "@/components/adapters";
import { useChips } from "@/lib/api";

export function PillDemo() {
  const chips = useChips();
  if (!chips.data) return <p className="text-sm text-muted-foreground">Loading chips…</p>;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {chips.data.categories.map((c) => (
          <Pill key={c.id} asChild tone="soft" color={c.color}>
            <button type="button">{c.chips[0]?.label}</button>
          </Pill>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        {chips.data.categories.map((c) => (
          <Pill key={c.id} color={c.color} onRemove={() => undefined} removeLabel={`Remove ${c.chips[0]?.label}`}>
            {c.chips[0]?.label}
          </Pill>
        ))}
      </div>
      <div className="flex items-center gap-3">
        <MonoStat label="Tempo" value={90} unit="BPM" />
        <MonoStat label="Key" value={null} />
        <LicenseBadge license="CC-BY-4.0" attribution={'"Velvet Static" by The Quiet Arcade, licensed under CC BY 4.0'} />
      </div>
      <Attribution text={'"Velvet Static" by The Quiet Arcade, licensed under CC BY 4.0'} />
    </div>
  );
}
