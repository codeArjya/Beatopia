"use client";

import { useDndContext, useDroppable } from "@dnd-kit/core";
import { horizontalListSortingStrategy, SortableContext, useSortable } from "@dnd-kit/sortable";
import { cn } from "cn";
import type { CSSProperties } from "react";

import { AppInput, Pill } from "@/components/adapters";
import type { IndexedChip } from "@/lib/search/chips";
import { parseDragId, SEARCH_BAR_ID } from "@/lib/search/dnd";
import type { SearchAction, SearchState } from "@/lib/search/state";

type SearchBarProps = {
  state: SearchState;
  index: ReadonlyMap<string, IndexedChip>;
  dispatch: (a: SearchAction) => void;
};

/** Stacked chips (sortable pills) before the text input. Drop target for tray chips. Must sit inside <SearchDnd>. */
export function SearchBar({ state, index, dispatch }: SearchBarProps) {
  const { setNodeRef } = useDroppable({ id: SEARCH_BAR_ID });
  const { active, over } = useDndContext();
  // Highlight while a tray chip hovers the bar or any pill in it.
  const receiving = active != null && over != null && parseDragId(active.id).from === "tray";

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "flex min-h-11 flex-wrap items-center gap-1.5 rounded-lg border bg-card px-2 py-1.5 transition-colors",
        "focus-within:ring-[3px] focus-within:ring-ring/50",
        receiving && "border-ring bg-accent/40 ring-[3px] ring-ring/50",
      )}
    >
      <SortableContext items={state.chips} strategy={horizontalListSortingStrategy}>
        {state.chips.map((id) => (
          <SortablePill
            key={id}
            id={id}
            chip={index.get(id)}
            onRemove={() => dispatch({ type: "remove", id })}
          />
        ))}
      </SortableContext>
      <AppInput
        aria-label="Search text"
        placeholder={state.chips.length ? "Add words…" : "Describe a sound, or drag chips here…"}
        value={state.text}
        onChange={(e) => dispatch({ type: "setText", text: e.target.value })}
        onKeyDown={(e) => {
          if (e.key === "Backspace" && e.currentTarget.value === "" && state.chips.length) {
            e.preventDefault();
            dispatch({ type: "removeLast" });
          }
        }}
        className="h-8 min-w-40 flex-1 border-0 bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent"
      />
    </div>
  );
}

type SortablePillProps = { id: string; chip: IndexedChip | undefined; onRemove: () => void };

/**
 * A stacked chip. The label is the drag handle (activator), so the × button keeps its own click and keyboard
 * behavior: dnd-kit's KeyboardSensor ignores keys whose target isn't the activator node.
 */
function SortablePill({ id, chip, onRemove }: SortablePillProps) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id,
  });
  const label = chip?.label ?? id;
  // Translate only (no scale): pills have different widths. Written by hand; @dnd-kit/utilities isn't a direct dep.
  const style: CSSProperties = {
    transform: transform ? `translate3d(${Math.round(transform.x)}px, ${Math.round(transform.y)}px, 0)` : undefined,
    transition,
  };

  return (
    <Pill
      ref={setNodeRef}
      style={style}
      color={chip?.color}
      onRemove={onRemove}
      removeLabel={`Remove ${label}`}
      className={cn(isDragging && "opacity-40")}
    >
      <span
        ref={setActivatorNodeRef}
        {...attributes}
        {...listeners}
        aria-label={`${label}, search chip`}
        className="cursor-grab touch-none rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing"
      >
        {label}
      </span>
    </Pill>
  );
}
