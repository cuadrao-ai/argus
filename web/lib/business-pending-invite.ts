/**
 * The Business invitation an email link pointed at, kept until it is answered.
 * One owner for "which invite to open": the link's `invite` value is saved
 * here when the person arrives, before sign-up or sign-in, and whoever shows
 * invitations reads it from here. The server still decides who may accept it.
 */

import { readReturnPath } from "./auth-return-path";
import { readStored, removeStored, writeStored } from "./browser-storage";

const KEY = "cuadrao:pending_invite:v1";
const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function inviteIn(address: string): string | null {
  const query = address.includes("?") ? address.slice(address.indexOf("?") + 1) : "";
  const value = new URLSearchParams(query).get("invite");
  return value && ID.test(value) ? value.toLowerCase() : null;
}

/** Saves the invite named by the Business address, or by the page sign-in returns to. */
export function capturePendingInvite(pathname: string, search: string): void {
  const id = pathname === "/biz" ? inviteIn(`?${search.replace(/^\?/, "")}`) : inviteIn(readReturnPath(search) ?? "");
  if (id) writeStored(KEY, id);
}

export function pendingInviteId(): string | null {
  const stored = readStored(KEY);
  return stored && ID.test(stored) ? stored : null;
}

/** Called once the invitation is accepted or no longer offered to this person. */
export function forgetPendingInvite(): void {
  removeStored(KEY);
}
