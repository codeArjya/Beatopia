// Drag-and-drop rules for the chip tray → search bar, and for reordering stacked pills.
// Pure: ids, drop → reducer actions, collision detection, screen-reader announcements. Components live in
// components/search/{SearchDnd,SearchBar,ChipTray}.tsx.
import {
  closestCenter,
  pointerWithin,
  type Announcements,
  type CollisionDetection,
  type UniqueIdentifier,
} from "@dnd-kit/core";

import type { SearchAction } from "./state";

/** Droppable id of the search bar itself (the area around and between the pills). */
export const SEARCH_BAR_ID = "search-bar";

/** Tray chips are dragged as `tray:{chipId}`; stacked pills use the bare chip id (the SortableContext items). */
const TRAY_PREFIX = "tray:";

export const trayDragId = (chipId: string) => `${TRAY_PREFIX}${chipId}`;

export type DragSource = { from: "tray" | "pill"; chipId: string };

export function parseDragId(id: UniqueIdentifier): DragSource {
  const s = String(id);
  return s.startsWith(TRAY_PREFIX) ? { from: "tray", chipId: s.slice(TRAY_PREFIX.length) } : { from: "pill", chipId: s };
}

/**
 * What a drop does to the search state.
 * - Tray chip on the bar → append. Tray chip on a pill → insert before that pill. Already stacked → nothing.
 * - Pill on another pill → move into its slot. Pill on the bar's empty area → move to the end.
 */
export function dropActions(
  activeId: UniqueIdentifier,
  overId: UniqueIdentifier | null | undefined,
  chips: readonly string[],
): SearchAction[] {
  if (overId == null) return [];
  const { from, chipId } = parseDragId(activeId);
  const over = String(overId);
  const overPill = over !== SEARCH_BAR_ID && chips.includes(over) ? over : null;
  if (!overPill && over !== SEARCH_BAR_ID) return [];

  if (from === "tray") {
    if (chips.includes(chipId)) return [];
    const add: SearchAction = { type: "add", id: chipId };
    return overPill ? [add, { type: "move", id: chipId, overId: overPill }] : [add];
  }

  if (!chips.includes(chipId)) return [];
  const target = overPill ?? chips[chips.length - 1];
  return target && target !== chipId ? [{ type: "move", id: chipId, overId: target }] : [];
}

/**
 * Tray drags only land where the pointer actually is (dropping elsewhere does nothing), preferring a pill over
 * the bar so the drop can insert at that position. Pill drags sort among pills only (closestCenter, which is also
 * what keyboard sorting with sortableKeyboardCoordinates needs).
 */
export const searchCollision: CollisionDetection = (args) => {
  if (parseDragId(args.active.id).from === "tray") {
    const hits = pointerWithin(args);
    return [...hits.filter((h) => h.id !== SEARCH_BAR_ID), ...hits.filter((h) => h.id === SEARCH_BAR_ID)];
  }
  return closestCenter({
    ...args,
    droppableContainers: args.droppableContainers.filter((c) => c.id !== SEARCH_BAR_ID),
  });
};

/** Screen-reader text for drags. `label` maps a chip id to its label; `chips()` returns the current stack. */
export function searchAnnouncements(label: (chipId: string) => string, chips: () => readonly string[]): Announcements {
  const name = (id: UniqueIdentifier) => label(parseDragId(id).chipId);
  const position = (id: UniqueIdentifier) => {
    const list = chips();
    return `position ${list.indexOf(String(id)) + 1} of ${list.length}`;
  };
  const isTray = (id: UniqueIdentifier) => parseDragId(id).from === "tray";
  return {
    onDragStart: ({ active }) => `Picked up ${name(active.id)}.`,
    onDragOver: ({ active, over }) => {
      if (!over) return isTray(active.id) ? `${name(active.id)} is not over the search bar.` : undefined;
      if (isTray(active.id)) return `${name(active.id)} is over the search bar.`;
      return `${name(active.id)} moved to ${position(over.id)}.`;
    },
    onDragEnd: ({ active, over }) => {
      if (isTray(active.id)) {
        return over ? `Added ${name(active.id)} to search.` : `${name(active.id)} was dropped outside the search bar.`;
      }
      return over ? `${name(active.id)} dropped at ${position(over.id)}.` : `${name(active.id)} dropped.`;
    },
    onDragCancel: ({ active }) => `Cancelled. ${name(active.id)} was not moved.`,
  };
}
