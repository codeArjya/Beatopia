"use client";

import { useState } from "react";
import type { Op } from "@/lib/types/api";
import { Button } from "@/components/ui/button";

interface Props {
  active: string;
  selection: [number, number];
  length: number;
  hasBeats: boolean;
  bpm: number | null;
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
  const [snap, setSnap] = useState<"none" | "beat" | "transient">("none");
  const [semitones, setSemitones] = useState(-3);
  const [targetBpm, setTargetBpm] = useState(120);
  const [keepPitch, setKeepPitch] = useState(false);
  const [filterType, setFilterType] = useState<"lowpass" | "highpass">("lowpass");
  const [frequency, setFrequency] = useState(1000);
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
      <label className="text-sm">Snap <select className="rounded border p-2" value={snap === "beat" && !props.hasBeats ? "none" : snap} onChange={(event) => setSnap(event.target.value as typeof snap)}>
        <option value="none">None (equal parts)</option><option value="beat" disabled={!props.hasBeats}>Beat</option><option value="transient">Transient</option>
      </select></label>
      <Button onClick={() => props.onApply([{ op: "slice", clip: props.active, count, snap: snap === "beat" && !props.hasBeats ? "none" : snap }])}>Chop into {count}</Button>
      <Button variant="outline" onClick={() => props.onApply([{ op: "reverse", clip: props.active }])}>Reverse</Button>
      <Button variant="outline" disabled={!props.canUndo} onClick={props.onUndo}>Undo</Button>
      <Button variant="outline" disabled={!props.canRedo} onClick={props.onRedo}>Redo</Button>
    </div>
    {!props.hasBeats && <p className="text-muted-foreground text-sm">Beat snap requires known BPM and beat positions. Equal parts and transient snap are available.</p>}
    <div className="flex flex-wrap items-end gap-3">
      <label className="text-sm">Semitones<input className="mt-1 block w-28 rounded border p-2" type="number" min={-24} max={24} step={1} value={Number.isFinite(semitones) ? semitones : ""} onChange={(event) => setSemitones(event.target.valueAsNumber)} /></label>
      <Button variant="outline" onClick={() => props.onApply([{ op: "repitch", clip: props.active, semitones }])}>Repitch (changes duration)</Button>
      <Button variant="outline" onClick={() => props.onApply([{ op: "pitch_shift", clip: props.active, semitones }])}>Pitch shift (same duration)</Button>
    </div>
    <div className="flex flex-wrap items-end gap-3">
      <label className="text-sm">Target BPM<input className="mt-1 block w-28 rounded border p-2" type="number" min={40} max={240} value={Number.isFinite(targetBpm) ? targetBpm : ""} onChange={(event) => setTargetBpm(event.target.valueAsNumber)} /></label>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={keepPitch} onChange={(event) => setKeepPitch(event.target.checked)} />Keep pitch</label>
      <Button variant="outline" disabled={props.bpm == null} onClick={() => props.onApply([{ op: "stretch_to_bpm", clip: props.active, target_bpm: targetBpm, keep_pitch: keepPitch }])}>Fit to BPM</Button>
      <p className="text-muted-foreground text-sm">{props.bpm == null ? "Tempo fit requires known source BPM." : `Fit uses original track tempo: ${props.bpm} BPM.`}</p>
    </div>
    <div className="flex flex-wrap items-end gap-3">
      <label className="text-sm">Filter<select className="mt-1 block rounded border p-2" value={filterType} onChange={(event) => setFilterType(event.target.value as typeof filterType)}><option value="lowpass">Low-pass</option><option value="highpass">High-pass</option></select></label>
      <label className="text-sm">Cutoff (Hz)<input className="mt-1 block w-28 rounded border p-2" type="number" min={20} max={20000} value={Number.isFinite(frequency) ? frequency : ""} onChange={(event) => setFrequency(event.target.valueAsNumber)} /></label>
      <Button variant="outline" onClick={() => props.onApply([{ op: "filter", clip: props.active, type: filterType, freq_hz: frequency }])}>Apply filter</Button>
    </div>
  </fieldset>;
}
