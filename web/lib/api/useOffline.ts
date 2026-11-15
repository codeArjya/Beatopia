"use client";

import { useSyncExternalStore } from "react";

import { fixturesActive, USE_FIXTURES } from "./client";
import { isOffline } from "./offline";

const noSubscribe = () => () => undefined;

/** `{ offline, fixtures }` for this page load. The server render assumes the build-time mode (no hydration error). */
export function useDataMode(): { offline: boolean; fixtures: boolean } {
  const offline = useSyncExternalStore(noSubscribe, isOffline, () => false);
  const fixtures = useSyncExternalStore(noSubscribe, fixturesActive, () => USE_FIXTURES);
  return { offline, fixtures };
}
