import { Suspense } from "react";
import { notFound } from "next/navigation";
import { EditorClient } from "@/components/editor/editor-client";
import detail from "@/lib/audio/acceptance/hero-storage.json";
import type { TrackDetail } from "@/lib/types/api";

type CheckParams = Promise<{ case?: string }>;
async function CheckEditor({ searchParams }: { searchParams: CheckParams }) {
  const scenario = (await searchParams).case ?? "normal";
  let metadata = detail as TrackDetail;
  if (scenario === "missing-bpm") metadata = { ...metadata, track: { ...metadata.track, bpm: null }, beat_times: [] };
  if (scenario === "http-error") metadata = { ...metadata, audio_url: "/fixtures/audio/ws4-missing-check.wav" };
  if (scenario === "decode-error") metadata = { ...metadata, audio_url: "/editor/audio-checks" };
  const expectations: Record<string, string> = {
    normal: "Expected: live waveform, editing, playback and WAV download work.",
    "missing-bpm": "Expected: seconds timeline; beat snap and Fit to BPM unavailable. Other edits remain available.",
    "http-error": "Expected failure: HTTP 404 from an intentionally missing audio file. Select normal to recover.",
    "decode-error": "Expected failure: unsupported/corrupt audio message from an intentionally non-audio URL. Select normal to recover.",
  };
  return <><p className="text-sm">Test scenario: {scenario}. Error/BPM cases deliberately alter the development snapshot.</p>
    <p className="text-sm">{expectations[scenario] ?? expectations.normal}</p>
    <EditorClient key={scenario} acceptanceDetail={metadata} /></>;
}

export default function LiveEditorChecksPage({ searchParams }: { searchParams: CheckParams }) {
  if (process.env.NODE_ENV !== "development" || process.env.NEXT_PUBLIC_USE_FIXTURES !== "1") notFound();
  return <main className="mx-auto max-w-5xl space-y-6 px-6 py-12">
    <h1 className="text-2xl font-semibold">Development hero editor check</h1>
    <p>Real public audio with a database metadata snapshot. This uses the same editor and audio engine; production API and telemetry integration are not tested.</p>
    <a className="block underline" href="/editor/live-audio-checks">Open automated live storage checks</a>
    <nav className="flex flex-wrap gap-4 text-sm" aria-label="Development test scenarios">
      {["normal", "missing-bpm", "http-error", "decode-error"].map((scenario) => <a className="underline" key={scenario}
        href={`/editor/live-editor-checks?track=jam_1047157&start=5&end=15&stem=mix&case=${scenario}`}>{scenario}</a>)}
      <a className="underline" href="/editor/live-editor-checks?track=jam_1047157&start=5&end=15&stem=drums">drums</a>
    </nav>
    <Suspense fallback={<p>Loading editor…</p>}><CheckEditor searchParams={searchParams} /></Suspense>
  </main>;
}
