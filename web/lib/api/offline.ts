// Offline backup demo (handoff §11): `?offline=1` on any page switches lib/api to shared/fixtures at runtime, and
// the choice survives reloads in sessionStorage. `?offline=0` turns it off again. Decided once per page load.

export const OFFLINE_KEY = "beatopia_offline";

type SessionStore = Pick<Storage, "getItem" | "setItem" | "removeItem">;

/** Pure: read (and persist) the offline choice from a URL query string and a session store. */
export function resolveOffline(search: string, store: SessionStore | null): boolean {
  const flag = new URLSearchParams(search).get("offline");
  try {
    if (flag === "1") {
      store?.setItem(OFFLINE_KEY, "1");
      return true;
    }
    if (flag === "0") {
      store?.removeItem(OFFLINE_KEY);
      return false;
    }
    return store?.getItem(OFFLINE_KEY) === "1";
  } catch {
    // Storage blocked (private mode, sandboxed iframe): the URL flag alone still works for this load.
    return flag === "1";
  }
}

let cached: boolean | null = null;

/** True when this page load runs on fixtures because of `?offline=1` (always false on the server). */
export function isOffline(): boolean {
  if (typeof window === "undefined") return false;
  if (cached === null) {
    let store: SessionStore | null = null;
    try {
      store = window.sessionStorage;
    } catch {
      store = null;
    }
    cached = resolveOffline(window.location.search, store);
  }
  return cached;
}

/** URL of the current page with the offline flag set to `on`, for the banner's toggle link. */
export function offlineToggleHref(href: string, on: boolean): string {
  const url = new URL(href);
  url.searchParams.set("offline", on ? "1" : "0");
  return url.pathname + url.search + url.hash;
}
