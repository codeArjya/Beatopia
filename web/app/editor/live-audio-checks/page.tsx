import { notFound } from "next/navigation";
import { AudioChecks } from "@/components/editor/audio-checks";
import detail from "@/lib/audio/acceptance/hero-storage.json";
import type { TrackDetail } from "@/lib/types/api";

export default function LiveAudioChecksPage() {
  if (process.env.NODE_ENV !== "development" || process.env.NEXT_PUBLIC_USE_FIXTURES !== "1") notFound();
  return <AudioChecks liveDetail={detail as TrackDetail} />;
}
