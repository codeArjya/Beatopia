"use client";

import { useState } from "react";
import { EditorClient } from "./editor-client";

/** Mounted only by the development/fixture source-checks route. */
export function EditorLifecycleChecks() {
  const [mounted, setMounted] = useState(false);
  return <section aria-label="Editor lifecycle checks" className="space-y-4 border-t p-8">
    <h2>Editor mount/unmount checks</h2>
    <p>Mount the actual editor, import or play audio, then unmount while inspecting resource cleanup. Remount starts a fresh editor.</p>
    <button className="rounded border p-2" onClick={() => setMounted((value) => !value)}>
      {mounted ? "Unmount test editor" : "Mount test editor"}
    </button>
    {mounted && <EditorClient />}
  </section>;
}
