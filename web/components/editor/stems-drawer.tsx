"use client";

import { useState } from "react";
import type { Stem, TrackDetail } from "@/lib/types/api";
import { StemsDrawer as LibraryStemsDrawer } from "@/components/stems/StemsDrawer";
import { Button } from "@/components/ui/button";

interface Props {
  detail: TrackDetail;
  start: number;
  end: number;
  disabled: boolean;
  onOpen: () => void;
  onSelect: (stem: Stem) => Promise<boolean>;
}

/** WS3 owns requesting/polling/preview; WS4 owns decoding and atomic source history. */
export function StemsDrawer({ detail, start, end, disabled, onOpen, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const [retryStem, setRetryStem] = useState<Stem | null>(null);
  const choose = async (stem: Stem) => {
    // Close before decoding so the editor's progress/error/retry remains visible.
    setOpen(false);
    setRetryStem(null);
    if (!await onSelect(stem)) setRetryStem(stem);
  };
  return <div className="space-y-2">
    <div className="flex gap-2">
      <Button variant="outline" disabled={disabled} onClick={() => { onOpen(); setOpen(true); }}>Stems</Button>
      {retryStem && <Button variant="outline" disabled={disabled} onClick={() => void choose(retryStem)}>Retry adding {retryStem.stem}</Button>}
    </div>
    <LibraryStemsDrawer trackId={detail.track.id} startS={start} endS={end} trackTitle={detail.track.title}
      open={open} onOpenChange={setOpen} onPick={(stem) => { if (!disabled) void choose(stem); }} />
  </div>;
}
