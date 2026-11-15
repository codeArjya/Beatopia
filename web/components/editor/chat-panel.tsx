"use client";

import { useEffect, useState } from "react";
import { useStore } from "zustand";
import { useAssist, USE_FIXTURES } from "@/lib/api";
import { assistUnavailable } from "@/lib/audio/assist";
import { describeOp } from "@/lib/audio/editor-actions";
import { duration } from "@/lib/audio/pcm";
import { createAssistStore } from "@/stores/assist";
import type { EditorStoreApi } from "@/stores/editor";
import { Button } from "@/components/ui/button";

export function ChatPanel({ editor }: { editor: EditorStoreApi }) {
  const mutation = useAssist();
  const [store] = useState(() => createAssistStore(editor, mutation.mutateAsync));
  const chat = useStore(store);
  const state = useStore(editor);
  const [text, setText] = useState("");
  useEffect(() => () => store.getState().clear(), [store]);
  const unavailable = assistUnavailable(state.current?.wire ?? null);
  const stale = !!chat.proposal && chat.proposal.revision !== state.revision;
  const disabled = !!unavailable || state.pending || chat.pending;
  return <aside aria-label="Edit assist" data-editor-shortcuts="off" className="space-y-3 rounded-xl border p-4 lg:sticky lg:top-4 lg:self-start">
    <h3 className="font-medium">Edit assist</h3>
    <p className="text-muted-foreground text-sm">{USE_FIXTURES ? "Fixture suggestion" : "Ask for an edit"} · Review every suggestion before applying it.</p>
    {unavailable && <p className="text-sm">{unavailable}</p>}
    <ol aria-label="Assist conversation" className="max-h-80 space-y-3 overflow-y-auto text-sm">
      {chat.messages.map((message, index) => <li key={index} className="whitespace-pre-wrap break-words"><strong>{message.role === "user" ? "You" : "Assist"}: </strong>{message.content}</li>)}
    </ol>
    <form onSubmit={(event) => { event.preventDefault(); if (!disabled && !chat.proposal && text.trim()) { void chat.send(text); setText(""); } }} className="space-y-2">
      <label className="block text-sm">Describe an edit<textarea className="mt-1 min-h-24 w-full rounded border p-2" value={text} onChange={(event) => setText(event.target.value)} disabled={disabled || !!chat.proposal} /></label>
      <Button type="submit" disabled={disabled || !!chat.proposal || !text.trim()}>Ask assist</Button>
    </form>
    {chat.pending && <p role="status">Preparing suggestion… Manual controls remain available.</p>}
    {chat.proposal && <section aria-label="Proposed edits" className="space-y-2 text-sm">
      <h4 className="font-medium">Proposed edits</h4>
      <ol className="list-inside list-decimal">{chat.proposal.response.ops.map((op, index) => <li key={index}>{describeOp(op)}</li>)}</ol>
      <p>Result: {duration(chat.proposal.evaluation.rendered).toFixed(3)} s · {chat.proposal.evaluation.rendered.channels.length} channels</p>
      {stale && <p role="alert">The editor changed. Discard this preview and ask again.</p>}
      <div className="flex gap-2"><Button disabled={disabled || stale} onClick={() => void chat.apply()}>Apply suggestion</Button><Button variant="outline" disabled={chat.pending} onClick={chat.discard}>Discard</Button></div>
    </section>}
    {chat.error && <p role="alert" className="break-words text-sm">{chat.error} Your audio is unchanged.</p>}
    {chat.retryMessages && <Button variant="outline" disabled={disabled} onClick={() => void chat.retry()}>Retry assist</Button>}
    {chat.notice && <p role="status" className="text-sm">{chat.notice}</p>}
  </aside>;
}
