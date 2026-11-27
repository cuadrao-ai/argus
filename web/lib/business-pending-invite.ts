/**
 * The Business invitation an email link pointed at, kept until it is answered.
 * One owner for "which invite to open": arriving moves the link's `invite`
 * value out of the address and into this store, and whoever shows invitations
 * reads it from here. The server still decides who may accept it.
 */

import { readReturnPath } from "./auth-return-path";
import { readStored, removeStored, writeStored } from "./browser-storage";

const KEY = "cuadrao:pending_invite:v1";
const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function inviteIn(query: string): string | null {
  const value = new URLSearchParams(query).get("invite");
  return value && ID.test(value) ? value.toLowerCase() : null;
}

/**
 * Saves the invite the address names. At the Business address the value then
 * leaves the address, so a reload cannot bring back an invite already answered.
 * Before sign-in it rides in the page sign-in returns to, and stays there.
 */
export function capturePendingInvite(): void {
  const { pathname, search, hash } = window.location;
  if (pathname !== "/biz") {
    const returning = readReturnPath(search) ?? "";
    const id = inviteIn(returning.slice(returning.indexOf("?") + 1));
    if (id) writeStored(KEY, id);
    return;
  }
  const params = new URLSearchParams(search);
  if (!params.has("invite")) return;
  const id = inviteIn(search);
  if (id) writeStored(KEY, id);
  params.delete("invite");
  const query = params.toString();
  window.history.replaceState(window.history.state, "", `${pathname}${query ? `?${query}` : ""}${hash}`);
}

export function pendingInviteId(): string | null {
  const stored = readStored(KEY);
  return stored && ID.test(stored) ? stored : null;
}

/** Called once the invitation is accepted or no longer offered to this person. */
export function forgetPendingInvite(): void {
  removeStored(KEY);
}
