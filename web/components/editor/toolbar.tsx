"use client";

import { useState } from "react";
import type { Op } from "@/lib/types/api";
import { Button } from "@/components/ui/button";

interface Props {
  active: string;
  selection: [number, number];
  length: number;
  hasBeats: boolean;
  disabled: boolean;
  canUndo: boolean;
  canRedo: boolean;
  onSelect: (range: [number, number]) => void;
  onApply: (ops: Op[]) => void;
  onUndo: () => void;
  onRedo: () => void;
}
export function Toolbar(props: Props) {
  const [count, setCount] = useState(4);
  const [snap, setSnap] = useState<"none" | "beat">("none");
  return <fieldset disabled={props.disabled} className="space-y-4">
    <legend className="mb-2 font-medium">Edit {props.active}</legend>
    <div className="flex flex-wrap items-end gap-3">
      {(["Selection start", "Selection end"] as const).map((label, index) => <label key={label} className="text-sm">
        {label} (s)
        <input className="border-input mt-1 block w-32 rounded-md border px-2 py-1" type="number" min={0} max={props.length} step="0.001"
          value={Number(props.selection[index].toFixed(6))}
          onChange={(event) => { const range: [number, number] = [...props.selection]; range[index] = event.target.valueAsNumber; props.onSelect(range); }} />
      </label>)}
      <Button variant="outline" onClick={() => props.onSelect([0, props.length])}>Select all</Button>
      <Button variant="outline" onClick={() => props.onApply([{ op: "trim", clip: props.active, start_s: props.selection[0], end_s: props.selection[1] }])}>Trim to selection</Button>
    </div>
    <div className="flex flex-wrap items-center gap-2">
      <label className="text-sm">Slices <select className="rounded border p-2" value={count} onChange={(event) => setCount(Number(event.target.value))}>
        {[2, 4, 8, 16].map((value) => <option key={value}>{value}</option>)}
      </select></label>
      <label className="text-sm">Snap <select className="rounded border p-2" value={snap} onChange={(event) => setSnap(event.target.value as "none" | "beat")}>
        <option value="none">None (equal parts)</option><option value="beat" disabled={!props.hasBeats}>Beat</option>
      </select></label>
      <Button onClick={() => props.onApply([{ op: "slice", clip: props.active, count, snap }])}>Chop into {count}</Button>
      <Button variant="outline" onClick={() => props.onApply([{ op: "reverse", clip: props.active }])}>Reverse</Button>
      <Button variant="outline" disabled={!props.canUndo} onClick={props.onUndo}>Undo</Button>
      <Button variant="outline" disabled={!props.canRedo} onClick={props.onRedo}>Redo</Button>
    </div>
    {!props.hasBeats && <p className="text-muted-foreground text-sm">Beat snap requires known BPM and beat positions. Equal parts is available.</p>}
  </fieldset>;
}
