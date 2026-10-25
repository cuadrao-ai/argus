/**
 * The Business the person chose to work in, as the grant that admits them.
 * The server proves the grant on every request and takes the Business from
 * it; this is only the client's memory of the choice, per viewer. No value
 * means the person's own Business.
 */

import { readStored, removeStored, writeStored } from "./browser-storage";

export const LOCAL_BUSINESS_PREFIX = "local-business-";
const localGrant = (value: string) => /^local-business-[a-z0-9-]{1,64}$/i.test(value);

const KEY = "argus:business-grant:v1";
let current: string | null | undefined;
let owner: string | null = null;
const listeners = new Set<() => void>();

function read(): string | null {
  const stored = readStored(KEY);
  if (!stored) return null;
  try {
    const choice = JSON.parse(stored);
    const previewLocal = process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true" && typeof choice.grantId === "string" && localGrant(choice.grantId);
    return choice.userId === owner && typeof choice.grantId === "string" && ((Boolean(owner) && /^[0-9a-f-]{36}$/i.test(choice.grantId)) || previewLocal) ? choice.grantId : null;
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

/** The only Business a viewer can enter when they have no Business of their own. */
export function soleClientGrantId(spaces: readonly { grant_id: string; role: string }[]): string | null {
  if (spaces.length !== 1 || spaces[0].role === "owner") return null;
  return spaces[0].grant_id;
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
  return grant && !grant.startsWith(LOCAL_BUSINESS_PREFIX) ? { [GRANT_HEADER]: grant } : {};
}

/** A refusal that means the chosen grant is no longer the caller's or live. */
export function grantNotLive(error: unknown): boolean {
  return (error as { code?: unknown } | null)?.code === "business_grant_not_live";
}
