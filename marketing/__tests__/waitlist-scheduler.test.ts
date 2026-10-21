import { expect, test } from "bun:test";
import { handleReminderRequest, STAGING_URL } from "../../supabase/functions/waitlist-reminders/handler";

const env = { SUPABASE_URL: STAGING_URL, SUPABASE_SERVICE_ROLE_KEY: "fixture-service-key", CUADRAO_WAITLIST_SCHEDULER_KEY: "fixture-scheduler-key", RESEND_API_KEY: "fixture-mail", MARKETING_WAITLIST_FROM: "Cuadrao <hola@cuadrao.ai>", MARKETING_POSTAL_ADDRESS: "Fixture address", CUADRAO_WAITLIST_ORIGIN: "https://cuadrao.example.test" };
const row = { verification_id: "ab".repeat(32), email: "fixture@example.test", confirmed_at: null, last_confirmation_sent_at: "2026-10-16T12:00:00Z" };
const request = (key = env.CUADRAO_WAITLIST_SCHEDULER_KEY) => new Request(`${STAGING_URL}/functions/v1/waitlist-reminders`, { method: "POST", headers: { "X-Cuadrao-Waitlist-Scheduler-Key": key } });
function transport(outcome = 200, active = true) {
  const calls: { url: string; body: unknown; key: string | null }[] = [];
  const fetcher = (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null, key: new Headers(init?.headers).get("Idempotency-Key") });
    if (url.endsWith("/cuadrao_waitlist_reminders")) return Response.json([row]);
    if (url.includes("cuadrao_early_access_signups?")) return Response.json(active ? [row] : []);
    if (url.endsWith("/cuadrao_waitlist_release")) return Response.json(null);
    if (url === "https://api.resend.com/emails") return Response.json({}, { status: outcome });
    throw new Error("Unexpected network request");
  }) as typeof fetch;
  return { calls, fetcher };
}

test("scheduler rejects missing, incorrect and Unicode auth before any network call", async () => {
  const f = transport();
  for (const key of ["", "wrong", "é".repeat(env.CUADRAO_WAITLIST_SCHEDULER_KEY.length)]) expect((await handleReminderRequest(request(key), env, f.fetcher)).status).toBe(401);
  expect(f.calls).toEqual([]);
});
test("scheduler rejects any other project and incomplete configuration before reserving", async () => {
  const f = transport();
  for (const extra of [{ SUPABASE_URL: "https://other-project.supabase.co" }, { RESEND_API_KEY: "" }, { CUADRAO_WAITLIST_ORIGIN: "http://example.test" }]) expect((await handleReminderRequest(request(), { ...env, ...extra }, f.fetcher)).status).toBe(503);
  expect(f.calls).toEqual([]);
});
test("scheduler reserves two reminders, rechecks active state and uses the canonical mail renderer without purge", async () => {
  const f = transport(); const response = await handleReminderRequest(request(), env, f.fetcher);
  expect(response.status).toBe(200); expect(await response.json()).toEqual({ remindersSent: 1, remindersFailed: 0 });
  expect(f.calls[0].body).toEqual({ p_limit: 2 });
  expect(f.calls).toHaveLength(3);
  expect(f.calls[2].body).toMatchObject({ to: [row.email], reply_to: "hola@cuadrao.ai" });
  expect(f.calls[2].key).toStartWith("waitlist-reminder-");
});
test("a removed row sends no reminder", async () => {
  const f = transport(200, false); const response = await handleReminderRequest(request(), env, f.fetcher);
  expect(await response.json()).toEqual({ remindersSent: 0, remindersFailed: 0 }); expect(f.calls).toHaveLength(2);
});
test("refused delivery reports failure and releases the same reservation; unknown delivery retains it", async () => {
  const f = transport(400); const response = await handleReminderRequest(request(), env, f.fetcher);
  expect(response.status).toBe(503); expect(await response.json()).toEqual({ remindersSent: 0, remindersFailed: 1 });
  expect(f.calls[3].body).toEqual({ p_verification_id: row.verification_id, p_reserved_at: row.last_confirmation_sent_at, p_reminder: true });
  const g = transport(500); expect((await handleReminderRequest(request(), env, g.fetcher)).status).toBe(503);
  expect(g.calls).toHaveLength(4); expect(g.calls[2].key).toBe(g.calls[3].key); expect(g.calls[2].body).toEqual(g.calls[3].body);
});
test("method and database errors cannot report successful maintenance", async () => {
  const f = transport(); expect((await handleReminderRequest(new Request(STAGING_URL), env, f.fetcher)).status).toBe(405);
  const failing = (async () => { throw new Error("private provider detail"); }) as typeof fetch;
  const response = await handleReminderRequest(request(), env, failing); expect(response.status).toBe(503); expect(await response.text()).not.toContain("private");
});


test("scheduler accepts only the approved subdomain sender and keeps the reply mailbox", async () => {
  const f = transport();
  const approved = "Cuadrao <no-responder@mail.cuadrao.ai>";
  expect((await handleReminderRequest(request(), { ...env, MARKETING_WAITLIST_FROM: approved }, f.fetcher)).status).toBe(200);
  expect(f.calls[2].body).toMatchObject({ from: approved, reply_to: "hola@cuadrao.ai" });
  for (const from of ["Cuadrao <other@mail.cuadrao.ai>", "Cuadrao <no-responder@other.cuadrao.ai>", "Cuadrao <no-responder@mail.cuadrao.ai.example.test>", "Other <no-responder@mail.cuadrao.ai>"]) {
    const rejected = transport();
    expect((await handleReminderRequest(request(), { ...env, MARKETING_WAITLIST_FROM: from }, rejected.fetcher)).status).toBe(503);
    expect(rejected.calls).toEqual([]);
  }
});


test("scheduler requires an explicit caller credential and retains the separate database credential", async () => {
  const f = transport();
  expect((await handleReminderRequest(request(), { ...env, CUADRAO_WAITLIST_SCHEDULER_KEY: undefined }, f.fetcher)).status).toBe(503);
  expect((await handleReminderRequest(request(), { ...env, CUADRAO_WAITLIST_SCHEDULER_KEY: " " }, f.fetcher)).status).toBe(503);
  expect((await handleReminderRequest(request(env.SUPABASE_SERVICE_ROLE_KEY), env, f.fetcher)).status).toBe(401);
  expect((await handleReminderRequest(new Request(STAGING_URL, { method: "POST", headers: { Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}` } }), env, f.fetcher)).status).toBe(401);
  expect((await handleReminderRequest(new Request(STAGING_URL, { method: "POST", headers: { Authorization: `Bearer ${env.CUADRAO_WAITLIST_SCHEDULER_KEY}` } }), env, f.fetcher)).status).toBe(401);
  expect((await handleReminderRequest(request(env.SUPABASE_SERVICE_ROLE_KEY), { ...env, CUADRAO_WAITLIST_SCHEDULER_KEY: env.SUPABASE_SERVICE_ROLE_KEY }, f.fetcher)).status).toBe(503);
  expect(f.calls).toEqual([]);
  const databaseHeaders: Headers[] = [];
  const fetcher = (async (input: string | URL | Request, init?: RequestInit) => {
    if (String(input).startsWith(STAGING_URL)) databaseHeaders.push(new Headers(init?.headers));
    return f.fetcher(input, init);
  }) as typeof fetch;
  expect((await handleReminderRequest(request(), env, fetcher)).status).toBe(200);
  expect(databaseHeaders).toHaveLength(2);
  for (const headers of databaseHeaders) {
    expect(headers.get("apikey")).toBe(env.SUPABASE_SERVICE_ROLE_KEY);
    expect(headers.get("authorization")).toBe(`Bearer ${env.SUPABASE_SERVICE_ROLE_KEY}`);
    expect(headers.get("x-cuadrao-waitlist-scheduler-key")).toBeNull();
  }
});
