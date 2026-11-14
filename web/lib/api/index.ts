// Public surface of lib/api. Import from "@/lib/api", not from the files inside.
export { api, ApiError, API_URL, USE_FIXTURES, type Api } from "./client";
export * from "./hooks";
export { keys } from "./keys";
export * from "./queries";
