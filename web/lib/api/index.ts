// Public surface of lib/api. Import from "@/lib/api", not from the files inside.
export { api, ApiError, API_URL, fixturesActive, USE_FIXTURES, type Api } from "./client";
export { isOffline, offlineToggleHref } from "./offline";
export * from "./hooks";
export { keys } from "./keys";
export * from "./queries";
