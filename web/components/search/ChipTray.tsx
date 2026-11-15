"use client";

import { useDraggable } from "@dnd-kit/core";
import { cn } from "cn";
import { ChevronDownIcon } from "lucide-react";
import { useId, useMemo, useState, type KeyboardEvent } from "react";

import { AppButton, AppInput, Pill, pillColorVar } from "@/components/adapters";
import { useChips } from "@/lib/api";
import { filterCategories } from "@/lib/search/chips";
import { trayDragId } from "@/lib/search/dnd";
import type { Chip, ChipCategory } from "@/lib/types/api";

type ChipTrayProps = {
  /** Chip ids currently stacked in the search. */
  selected: readonly string[];
  /** Click on a chip: add it, or remove it when already selected. */
  onToggle: (id: string) => void;
  className?: string;
};

/** Left tray: /chips grouped by category, collapsible, with a filter box. Click (or Enter/Space) adds a chip. */
export function ChipTray({ selected, onToggle, className }: ChipTrayProps) {
  const chips = useChips();
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(() => new Set());
  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const groups = useMemo(() => filterCategories(chips.data?.categories ?? [], query), [chips.data, query]);
  const filtering = query.trim() !== "";
  const filterId = useId();

  const toggleGroup = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const onFilterKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape" && query) {
      e.preventDefault();
      setQuery("");
    } else if (e.key === "Enter" && filtering) {
      // Enter in the filter adds the first match: type "rho", Enter → Rhodes.
      e.preventDefault();
      const first = groups[0]?.chips[0];
      if (first && !selectedSet.has(first.id)) onToggle(first.id);
      setQuery("");
    }
  };

  return (
    <nav aria-label="Search chips" className={cn("flex min-h-0 flex-col gap-3", className)}>
      <div className="space-y-1.5">
        <label htmlFor={filterId} className="eyebrow">
          Chips
        </label>
        <AppInput
          id={filterId}
          type="search"
          placeholder="Filter chips…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onFilterKey}
          autoComplete="off"
          spellCheck={false}
        />
      </div>

      {chips.isError ? (
        <div className="space-y-2 text-sm">
          <p className="text-destructive">Couldn&apos;t load chips.</p>
          <AppButton size="sm" variant="outline" onClick={() => void chips.refetch()}>
            Retry
          </AppButton>
        </div>
      ) : !chips.data ? (
        <TraySkeleton />
      ) : groups.length === 0 ? (
        <p className="text-sm text-muted-foreground">No chips match &ldquo;{query.trim()}&rdquo;.</p>
      ) : (
        <div className="-mr-2 min-h-0 flex-1 space-y-1 overflow-y-auto pr-2">
          {groups.map((g) => (
            <ChipGroup
              key={g.id}
              category={g}
              open={filtering || !collapsed.has(g.id)}
              canCollapse={!filtering}
              onToggleOpen={() => toggleGroup(g.id)}
              selected={selectedSet}
              onToggleChip={onToggle}
            />
          ))}
        </div>
      )}
    </nav>
  );
}

type ChipGroupProps = {
  category: ChipCategory;
  open: boolean;
  canCollapse: boolean;
  onToggleOpen: () => void;
  selected: ReadonlySet<string>;
  onToggleChip: (id: string) => void;
};

function ChipGroup({ category, open, canCollapse, onToggleOpen, selected, onToggleChip }: ChipGroupProps) {
  const panelId = useId();
  const picked = category.chips.filter((c) => selected.has(c.id)).length;
  return (
    <section aria-label={category.label}>
      <h3>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          disabled={!canCollapse}
          onClick={onToggleOpen}
          className="flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-left text-sm font-medium outline-none hover:bg-accent/50 focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default disabled:hover:bg-transparent"
        >
          <span aria-hidden className="size-2.5 rounded-full" style={{ background: pillColorVar(category.color) }} />
          <span className="flex-1">{category.label}</span>
          <span className="font-mono text-xs text-muted-foreground tabular-nums">
            {picked > 0 && <span className="sr-only">{picked} selected of </span>}
            {picked > 0 ? `${picked}/` : ""}
            {category.chips.length}
          </span>
          <ChevronDownIcon
            aria-hidden
            className={cn("size-4 text-muted-foreground transition-transform", !open && "-rotate-90")}
          />
        </button>
      </h3>
      <ul id={panelId} hidden={!open} className="flex flex-wrap gap-1.5 px-1 pt-1 pb-3">
        {category.chips.map((chip) => (
          <li key={chip.id}>
            <TrayChip chip={chip} color={category.color} selected={selected.has(chip.id)} onToggle={onToggleChip} />
          </li>
        ))}
      </ul>
    </section>
  );
}

type TrayChipProps = { chip: Chip; color: string; selected: boolean; onToggle: (id: string) => void };

/**
 * One tray chip. Click/Enter/Space toggles it; dragging it onto the search bar adds it (pointer only, so dnd-kit's
 * keyboard listeners and ARIA attributes would conflict with the button's own). Stacked chips can't be dragged again.
 */
function TrayChip({ chip, color, selected, onToggle }: TrayChipProps) {
  const { setNodeRef, listeners, isDragging } = useDraggable({ id: trayDragId(chip.id), disabled: selected });
  return (
    <Pill asChild tone="soft" color={color} selected={selected} className={cn(isDragging && "opacity-40")}>
      <button
        ref={setNodeRef}
        type="button"
        aria-pressed={selected}
        title={selected ? `Remove ${chip.label} from search` : `Add ${chip.label} to search (or drag it to the bar)`}
        onClick={() => onToggle(chip.id)}
        onPointerDown={(e) => listeners?.onPointerDown?.(e)}
      >
        {chip.label}
      </button>
    </Pill>
  );
}

function TraySkeleton() {
  return (
    <div aria-busy className="space-y-4" role="status">
      <span className="sr-only">Loading chips…</span>
      {[10, 6, 6, 4, 6].map((n, i) => (
        <div key={i} className="space-y-2">
          <div className="h-4 w-24 animate-pulse rounded bg-muted" />
          <div className="flex flex-wrap gap-1.5">
            {Array.from({ length: n }, (_, j) => (
              <div key={j} className="h-7 w-16 animate-pulse rounded-full bg-muted" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
