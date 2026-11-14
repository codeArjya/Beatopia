"use client";

import { DndContext, PointerSensor, closestCenter, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, horizontalListSortingStrategy, useSortable, arrayMove } from "@dnd-kit/sortable";
import type { Evaluation } from "@/lib/audio/evaluate";
import { arrangeOccurrence } from "@/lib/audio/editor-actions";
import { duration } from "@/lib/audio/pcm";
import type { Op } from "@/lib/types/api";
import { Button } from "@/components/ui/button";

interface Props {
  evaluation: Evaluation;
  selected: number;
  disabled: boolean;
  onSelect: (index: number) => void;
  onApply: (ops: Op[]) => void;
}
function Tile({ id, index, props }: { id: string; index: number; props: Props }) {
  const { setNodeRef, setActivatorNodeRef, transform, transition, attributes, listeners } = useSortable({ id, disabled: props.disabled });
  const clip = props.evaluation.order[index];
  return <li ref={setNodeRef} style={{ transform: transform ? `translate3d(${transform.x}px, ${transform.y}px, 0)` : undefined,
    transition }} className={`shrink-0 space-y-2 rounded-lg border p-3 ${props.selected === index ? "border-primary bg-muted" : ""}`}>
    <Button variant="ghost" disabled={props.disabled} aria-label={`Select occurrence ${index + 1}: ${clip}`} aria-pressed={props.selected === index} onClick={() => props.onSelect(index)}>
      {index + 1}. {clip} · {duration(props.evaluation.clips.get(clip)!.pcm).toFixed(3)} s
    </Button>
    <div className="flex gap-1">
      <Button variant="outline" disabled={props.disabled} {...attributes} {...listeners} ref={setActivatorNodeRef} aria-label={`Drag occurrence ${index + 1}`} style={{ touchAction: "none" }}>Drag</Button>
      <Button variant="outline" disabled={props.disabled || index === 0} aria-label={`Move occurrence ${index + 1} left`} onClick={() => props.onApply(arrangeOccurrence(props.evaluation.order, index, "left"))}>←</Button>
      <Button variant="outline" disabled={props.disabled || index === props.evaluation.order.length - 1} aria-label={`Move occurrence ${index + 1} right`} onClick={() => props.onApply(arrangeOccurrence(props.evaluation.order, index, "right"))}>→</Button>
      <Button variant="outline" disabled={props.disabled} aria-label={`Duplicate occurrence ${index + 1}`} onClick={() => props.onApply(arrangeOccurrence(props.evaluation.order, index, "duplicate"))}>+</Button>
    </div>
  </li>;
}
export function ArrangementLane(props: Props) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const ids = props.evaluation.order.map((clip, index) => `${index}:${clip}`);
  return <section aria-label="Arrangement" className="space-y-2">
    <h3 className="font-medium">Arrangement</h3>
    <p className="text-muted-foreground text-sm">Drag or use the arrows to reorder. + repeats a clip; edits affect every occurrence. Output limit: 60 seconds.</p>
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={({ active, over }) => {
      if (props.disabled || !over || active.id === over.id) return;
      const from = ids.indexOf(String(active.id)), to = ids.indexOf(String(over.id));
      if (from >= 0 && to >= 0) props.onApply([{ op: "arrange", order: arrayMove([...props.evaluation.order], from, to) }]);
    }}>
      <SortableContext items={ids} strategy={horizontalListSortingStrategy}>
        <ol className="flex gap-2 overflow-x-auto pb-3">{ids.map((id, index) => <Tile key={id} id={id} index={index} props={props} />)}</ol>
      </SortableContext>
    </DndContext>
  </section>;
}
