"use client";

import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import { useMemo, useState, type ReactNode } from "react";

import { Pill } from "@/components/adapters";
import type { IndexedChip } from "@/lib/search/chips";
import { dropActions, parseDragId, searchAnnouncements, searchCollision, type DragSource } from "@/lib/search/dnd";
import type { SearchAction } from "@/lib/search/state";

type SearchDndProps = {
  /** Stacked chip ids (search state order). */
  chips: readonly string[];
  index: ReadonlyMap<string, IndexedChip>;
  dispatch: (a: SearchAction) => void;
  children: ReactNode;
};

const SCREEN_READER_INSTRUCTIONS = {
  draggable:
    "To reorder a search chip, press Space or Enter to pick it up, use the arrow keys to move it, then press Space " +
    "or Enter to drop it, or Escape to cancel.",
};

/**
 * One DndContext for the tray and the search bar. Tray chips drag with the pointer only (their keyboard path is
 * Enter/click); stacked pills sort with pointer or keyboard. A move under 4 px stays a click.
 */
export function SearchDnd({ chips, index, dispatch, children }: SearchDndProps) {
  const [active, setActive] = useState<DragSource | null>(null);

  const announcements = useMemo(
    () => searchAnnouncements((id) => index.get(id)?.label ?? id, () => chips),
    [index, chips],
  );

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const onDragStart = ({ active }: DragStartEvent) => setActive(parseDragId(active.id));
  const onDragEnd = ({ active, over }: DragEndEvent) => {
    setActive(null);
    for (const a of dropActions(active.id, over?.id, chips)) dispatch(a);
  };

  const chip = active ? index.get(active.chipId) : undefined;

  return (
    <DndContext
      id="search-dnd"
      sensors={sensors}
      collisionDetection={searchCollision}
      accessibility={{ announcements, screenReaderInstructions: SCREEN_READER_INSTRUCTIONS }}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragCancel={() => setActive(null)}
    >
      {children}
      <DragOverlay dropAnimation={{ duration: 150, easing: "ease-out" }}>
        {active && (
          <Pill color={chip?.color} selected className="cursor-grabbing shadow-lg">
            {chip?.label ?? active.chipId}
          </Pill>
        )}
      </DragOverlay>
    </DndContext>
  );
}
