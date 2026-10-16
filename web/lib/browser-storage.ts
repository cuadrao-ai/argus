/**
 * The single door through which Argus persists anything in a browser.
 *
 * Every key is declared in STORAGE_REGISTRY with the privacy-policy concept
 * that discloses it, and the key type is closed, so an undeclared key is a type
 * error rather than a silent write. The privacy copy is derived from this
 * registry instead of being inferred by searching for call sites, because a
 * search only finds the syntactic forms someone thought to look for.
 *
 * An ESLint rule bans localStorage, sessionStorage, and document.cookie
 * everywhere but this file, so writing an undisclosed key means visibly
 * disabling that rule in review rather than aliasing a handle.
 */

/** The concepts the "Preferences you set" disclosure names to the reader. */
export type StorageConcept =
  | "language"
  | "appearance"
  | "layout"
  | "tips"
  | "temporary"
  | "campaign";

/**
 * Keys two dependencies own. We pass these to them explicitly rather than
 * letting the library pick its default, so the name is declared here and not
 * trusted to a package's internals. Both still route their writes themselves,
 * which is why the runtime observation test exists.
 */
export const THEME_STORAGE_KEY = "argus-theme";
export const LANGUAGE_STORAGE_KEY = "i18nextLng";

export const STORAGE_REGISTRY = {
  [LANGUAGE_STORAGE_KEY]: "language",
  [THEME_STORAGE_KEY]: "appearance",
  "argus:sidebar_mode": "layout",
  "cuadrao:business:sidebar_modes": "layout",
  "argus:command_palette_layout": "layout",
  "argus:guest-hint:confirmation:v1": "tips",
  "argus:guest-hint:result:v1": "tips",
  "argus:feedback-ask:v1": "tips",
  "argus.memoryOptOutConversations.v1": "temporary",
  "argus:receipt-followup:v1": "temporary",
  "argus:daily-cap-notice:v1": "temporary",
  "argus:landing-intent:v1": "campaign",
  "argus:landing-starter:v1": "temporary",
  // The Business the person was working in, as the grant that admits them.
  "argus:business-grant:v1": "layout",
} as const satisfies Record<string, StorageConcept>;

export type StorageKey = keyof typeof STORAGE_REGISTRY;

// The one sanctioned handle. This file is the sole exemption from the
// no-restricted-syntax ban in eslint.config.mjs.
const store = () => (typeof window === "undefined" ? null : window.localStorage);

/** Read a declared key. A blocked or missing store reads as absent. */
export function readStored(key: StorageKey): string | null {
  try {
    return store()?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

/** Write a declared key. Persistence is best effort and never throws. */
export function writeStored(key: StorageKey, value: string): void {
  try {
    store()?.setItem(key, value);
  } catch {
    // Storage may be unavailable; callers treat persistence as best effort.
  }
}

/** Remove a declared key. */
export function removeStored(key: StorageKey): void {
  try {
    store()?.removeItem(key);
  } catch {
    // Same as writeStored: absence is an acceptable outcome.
  }
}

/** A pending receiver follow-up lasts only in this tab, never across visits. */
export function readSessionStored(key: StorageKey): string | null {
  try { return typeof window === "undefined" ? null : window.sessionStorage.getItem(key); }
  catch { return null; }
}
export function writeSessionStored(key: StorageKey, value: string): boolean {
  try {
    if (typeof window === "undefined") return false;
    window.sessionStorage.setItem(key, value);
    return true;
  } catch { return false; }
}
export function removeSessionStored(key: StorageKey): void {
  try { if (typeof window !== "undefined") window.sessionStorage.removeItem(key); }
  catch { /* Already absent or storage unavailable. */ }
}
