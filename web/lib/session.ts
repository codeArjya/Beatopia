// Anonymous browser session id (CONTRACT §2): a random UUID kept in localStorage `session_id`.
// Read it only in event handlers / queryFn / mutationFn, never during render, so server and client HTML match.

const KEY = "session_id";
let memoryId: string | null = null;

function newId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `s_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
}

export function getSessionId(): string {
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      const existing = window.localStorage.getItem(KEY);
      if (existing) return existing;
      const id = memoryId ?? newId();
      window.localStorage.setItem(KEY, id);
      memoryId = id;
      return id;
    }
  } catch {
    // private mode / blocked storage: fall through to the in-memory id
  }
  memoryId ??= newId();
  return memoryId;
}
