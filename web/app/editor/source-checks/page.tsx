import { notFound } from "next/navigation";
import { AudioChecks } from "@/components/editor/audio-checks";

export default function SourceChecksPage() {
  if (process.env.NODE_ENV !== "development" || process.env.NEXT_PUBLIC_USE_FIXTURES !== "1") notFound();
  return <AudioChecks sourceChecks />;
}
