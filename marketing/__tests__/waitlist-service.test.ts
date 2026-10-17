import { expect, test } from "bun:test";
import { WindowLimiter } from "../lib/forms/rate-limit";
import { confirmWaitlist, handleWaitlistSignup, leaveWaitlist, maintainWaitlist, type WaitlistDeps } from "../lib/waitlist/service";
import { makeWaitlistToken } from "../lib/waitlist/tokens";
import type { WaitlistRow } from "../lib/waitlist/types";

const now = new Date("2026-10-16T12:00:00Z");
const row: WaitlistRow = { email: "fixture@example.test", email_digest: "cd".repeat(32), verification_id: "ab".repeat(32), created_at: now.toISOString(), confirmed_at: null, last_confirmation_sent_at: now.toISOString(), reminder_sent_at: null, privacy_policy_version: "2026-10-16" };
function fixture() {
  let saved: WaitlistRow | null = null;
  let storedInput: unknown;
  const sent: string[] = [];
  const deps: WaitlistDeps = {
    captchaSecret: "fixture-secret", hostname: "cuadrao.example.test", trustedClientIpHeader: null, now: () => now,
    perClient: new WindowLimiter(5, 3600000, () => now.getTime(), 100, false),
    fetch: (async () => Response.json({ success: true, hostname: "cuadrao.example.test", action: "personal_waitlist" })) as typeof fetch,
    store: {
      async register(input) { storedInput = input; if (saved) return null; saved = { ...row }; return saved; },
      async find() { return saved; },
      async confirm() { if (!saved) return null; saved.confirmed_at ??= now.toISOString(); return saved; },
      async leave() { saved = null; },
      async release() { if (saved) saved.last_confirmation_sent_at = null; },
      async purge() { return 0; },
      async reminders() { return saved && !saved.confirmed_at ? [saved] : []; },
    },
    async send(kind) { sent.push(kind); return "sent"; },
  };
  return { deps, sent, saved: () => saved, input: () => storedInput };
}
function request(extra: Record<string, unknown> = {}) {
  return new Request("https://cuadrao.example.test/api/waitlist/signups", { method: "POST", headers: { "Content-Type": "application/json", "Origin": "https://cuadrao.example.test", Host: "cuadrao.example.test" }, body: JSON.stringify({ email: row.email, captchaToken: "fixture-token", ...extra }) });
}

test("signup stores sanitized fields before sending; a duplicate sends nothing", async () => {
  const f = fixture();
  expect((await handleWaitlistSignup(request({ wish: "<b>Orden</b> https://bad.example.test" }), f.deps)).status).toBe(200);
  expect(f.input()).toMatchObject({ wish: "Orden" });
  expect(f.sent).toEqual(["confirmation"]);
  expect((await handleWaitlistSignup(request(), f.deps)).status).toBe(200);
  expect(f.sent).toHaveLength(1);
  expect(f.saved()?.confirmed_at).toBeNull();
});

test("CAPTCHA refusal or honeypot never creates a row or sends email", async () => {
  const f = fixture();
  f.deps.fetch = (async () => Response.json({ success: false })) as typeof fetch;
  expect((await handleWaitlistSignup(request(), f.deps)).status).toBe(400);
  expect((await handleWaitlistSignup(request({ website: "bot" }), f.deps)).status).toBe(200);
  expect(f.saved()).toBeNull(); expect(f.sent).toEqual([]);
});

test("digit runs drop only the optional text and IP never reaches storage", async () => {
  const f = fixture();
  expect((await handleWaitlistSignup(request({ wish: "Mi tarjeta 1234567890123", ip: "192.0.2.1" }), f.deps)).status).toBe(200);
  expect(f.input()).toEqual({ email: row.email, expenseMethod: null, wish: null });
});

test("store failure sends nothing; delivery failure is not reported as success", async () => {
  const f = fixture();
  f.deps.store.register = async () => { throw new Error("database unavailable"); };
  expect((await handleWaitlistSignup(request(), f.deps)).status).toBe(503); expect(f.sent).toEqual([]);
  const g = fixture(); g.deps.send = async () => "unknown";
  expect((await handleWaitlistSignup(request(), g.deps)).status).toBe(503);
  expect(g.saved()).not.toBeNull();
});

test("confirm sends welcome; leave removes the whole row and is idempotent", async () => {
  const f = fixture(); await handleWaitlistSignup(request(), f.deps);
  expect(await confirmWaitlist(makeWaitlistToken(row.verification_id, "confirm", now), f.deps)).toBe(true);
  expect(f.saved()?.confirmed_at).toBe(now.toISOString());
  expect(f.sent).toEqual(["confirmation", "welcome"]);
  const leave = makeWaitlistToken(row.verification_id, "leave", now);
  expect(await leaveWaitlist(leave, f.deps)).toBe(true);
  expect(f.saved()).toBeNull();
  expect(await leaveWaitlist(leave, f.deps)).toBe(true);
});

test("forged or expired confirmation and forged leave do not mutate", async () => {
  const f = fixture(); await handleWaitlistSignup(request(), f.deps);
  const expired = new Date(now.getTime() - 48 * 3600000);
  expect(await confirmWaitlist(makeWaitlistToken(row.verification_id, "confirm", expired), f.deps)).toBe(false);
  expect(await leaveWaitlist(makeWaitlistToken("cd".repeat(32), "leave", now), f.deps)).toBe(false);
  expect(f.saved()?.confirmed_at).toBeNull();
});

test("maintenance purges before reminder selection and never sends a launch notice", async () => {
  const f = fixture(); await handleWaitlistSignup(request(), f.deps);
  const order: string[] = [];
  f.deps.store.purge = async () => { order.push("purge"); return 2; };
  f.deps.store.reminders = async () => { order.push("reminders"); return [row]; };
  expect(await maintainWaitlist(f.deps)).toEqual({ purged: 2, remindersSent: 1, remindersFailed: 0 });
  expect(order).toEqual(["purge", "reminders"]); expect(f.sent).toEqual(["confirmation", "reminder"]);
});

test("only a definite provider refusal releases the email reservation", async () => {
  const f = fixture(); f.deps.send = async () => "refused";
  expect((await handleWaitlistSignup(request(), f.deps)).status).toBe(503);
  expect(f.saved()?.last_confirmation_sent_at).toBeNull();
  const g = fixture(); g.deps.send = async () => "unknown";
  expect((await handleWaitlistSignup(request(), g.deps)).status).toBe(503);
  expect(g.saved()?.last_confirmation_sent_at).toBe(row.last_confirmation_sent_at);
});
