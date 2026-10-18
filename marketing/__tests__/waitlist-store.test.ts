import { expect, test } from "bun:test";
import { waitlistStore } from "../lib/waitlist/store";
import { leaveWaitlist, confirmWaitlist } from "../lib/waitlist/service";
import { makeWaitlistToken } from "../lib/waitlist/tokens";

const id = "ab".repeat(32);
const now = () => new Date("2026-10-16T12:00:00Z");
function fixture() {
  let saved: object | null = { email: null, verification_id: id, privacy_policy_version: "2026-10-16", removed_at: now().toISOString() };
  const store = waitlistStore({ supabaseUrl: "http://fixture.local", supabaseServiceKey: "fixture" }, (async (input, init) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith("/rpc/cuadrao_waitlist_leave")) {
      if (JSON.parse(String(init?.body)).p_verification_id === id) saved = null;
      return Response.json(null);
    }
    if (init?.method !== "GET") throw new Error("Unexpected mutation");
    return Response.json(saved && !url.searchParams.has("removed_at") ? [saved] : []);
  }) as typeof fetch);
  return { store, saved: () => saved };
}

test("a soft-removed signup stays hidden from confirmation but is erased by its leave link", async () => {
  const f = fixture();
  expect(await confirmWaitlist(makeWaitlistToken(id, "confirm", now()), { store: f.store, now, send: async () => { throw new Error("Unexpected email"); } })).toBe(false);
  expect(f.saved()).toMatchObject({ verification_id: id });
  const leave = makeWaitlistToken(id, "leave", now());
  expect(await leaveWaitlist(leave, { store: f.store, now })).toBe(true);
  expect(f.saved()).toBeNull();
  expect(await leaveWaitlist(leave, { store: f.store, now })).toBe(true);
});

test("a forged link with a real removed-row prefix does not claim deletion or erase data", async () => {
  const f = fixture();
  const forged = makeWaitlistToken(id.slice(0, 32) + "cd".repeat(16), "leave", now());
  expect(await leaveWaitlist(forged, { store: f.store, now })).toBe(false);
  expect(f.saved()).toMatchObject({ verification_id: id });
});
