/**
 * The Business the person chose to work in, as the grant that admits them.
 * The server proves the grant on every request and takes the Business from
 * it; this is only the client's memory of the choice, per viewer. No value
 * means the person's own Business.
 */

import { readStored, removeStored, writeStored } from "./browser-storage";

const KEY = "argus:business-grant:v1";
let current: string | null | undefined;
let owner: string | null = null;
const listeners = new Set<() => void>();

function read(): string | null {
  const stored = readStored(KEY);
  if (!stored || !owner) return null;
  try {
    const choice = JSON.parse(stored);
    return choice.userId === owner && typeof choice.grantId === "string" && /^[0-9a-f-]{36}$/i.test(choice.grantId) ? choice.grantId : null;
  } catch { return null; }
}

export function synchronizeBusinessAccount(userId: string | null): void {
  if (owner === userId) return;
  owner = userId;
  current = read();
  if (!current) removeStored(KEY);
  for (const listener of listeners) listener();
}

export function getChosenGrant(): string | null {
  if (current === undefined) current = typeof window === "undefined" ? null : read();
  return current;
}

export function setChosenGrant(grantId: string | null): void {
  current = grantId;
  // The memory is a convenience; the server decides on every request.
  if (grantId) writeStored(KEY, JSON.stringify({ userId: owner, grantId }));
  else removeStored(KEY);
  for (const listener of listeners) listener();
}

export function subscribeChosenGrant(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The header every Business call carries while a grant is chosen. */
export const GRANT_HEADER = "X-Business-Grant";

export function chosenGrantHeader(): Record<string, string> {
  const grant = getChosenGrant();
  return grant ? { [GRANT_HEADER]: grant } : {};
}

/** A refusal that means the chosen grant is no longer the caller's or live. */
export function grantNotLive(error: unknown): boolean {
  return (error as { code?: unknown } | null)?.code === "business_grant_not_live";
}
