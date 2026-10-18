import { expect, test } from "bun:test";
import * as confirm from "../app/api/waitlist/confirm/route";
import * as leave from "../app/api/waitlist/leave/route";
import { makeWaitlistToken } from "../lib/waitlist/tokens";

const settings = { SUPABASE_URL: "https://database.example.test", SUPABASE_SERVICE_ROLE_KEY: "fixture-db", RESEND_API_KEY: "fixture-mail", MARKETING_WAITLIST_FROM: "Cuadrao <hola@cuadrao.ai>", MARKETING_POSTAL_ADDRESS: "Fixture address", CUADRAO_WAITLIST_ORIGIN: "https://cuadrao.example.test", CUADRAO_WAITLIST_TURNSTILE_SECRET: "fixture-captcha" };

test("email scanner GETs show POST buttons without reading, confirming, removing or sending", async () => {
  const before = Object.fromEntries(Object.keys(settings).map((key) => [key, process.env[key]]));
  const fetchBefore = globalThis.fetch;
  const calls: string[] = [];
  Object.assign(process.env, settings);
  globalThis.fetch = (async (input) => { calls.push(String(input)); return Response.json([]); }) as typeof fetch;
  try {
    for (const [route, action, label] of [[confirm, "confirm", "Confirmar mi correo"], [leave, "leave", "Salir de la lista"]] as const) {
      const token = makeWaitlistToken("ab".repeat(32), action, new Date());
      const response = await route.GET(new Request(`https://cuadrao.example.test/api/waitlist/${action}?token=${token}`));
      expect(response.status).toBe(200);
      const html = await response.text();
      expect(html).toContain('method="post"');
      expect(html).toContain(`<button type="submit">${label}</button>`);
      expect(html).toContain(`action="/api/waitlist/${action}?token=${token}"`);
      expect(response.headers.get("Cache-Control")).toBe("no-store");
      expect(response.headers.get("Referrer-Policy")).toBe("no-referrer");
      expect(response.headers.get("Content-Security-Policy")).toContain("form-action 'self'");
    }
    expect(calls).toEqual([]);
  } finally {
    globalThis.fetch = fetchBefore;
    for (const key of Object.keys(settings)) { if (before[key] === undefined) delete process.env[key]; else process.env[key] = before[key]; }
  }
});

test("explicit POST confirms while RFC 8058 one-click POST removes the signup", async () => {
  const before = Object.fromEntries(Object.keys(settings).map((key) => [key, process.env[key]]));
  const fetchBefore = globalThis.fetch;
  const now = new Date();
  let row: Record<string, unknown> | null = { verification_id: "ab".repeat(32), email: "fixture@example.test", confirmed_at: null, last_confirmation_sent_at: now.toISOString() };
  const writes: string[] = [];
  Object.assign(process.env, settings);
  globalThis.fetch = (async (input, init) => {
    const url = String(input);
    if (url.endsWith("cuadrao_waitlist_confirm")) { writes.push("confirm"); row!.confirmed_at = now.toISOString(); return Response.json([row]); }
    if (url.endsWith("cuadrao_waitlist_leave")) { writes.push("leave"); row = null; return Response.json(null); }
    if (url.includes("cuadrao_early_access_signups?")) return Response.json(row ? [row] : []);
    if (url.endsWith("/emails")) { writes.push("mail"); return Response.json({}); }
    throw new Error(`Unexpected fixture request ${init?.method}`);
  }) as typeof fetch;
  try {
    const confirmation = makeWaitlistToken(String(row!.verification_id), "confirm", now);
    const confirmPost = confirm.POST;
    expect(typeof confirmPost).toBe("function");
    expect((await confirmPost(new Request(`https://cuadrao.example.test/api/waitlist/confirm?token=${confirmation}`, { method: "POST" }))).status).toBe(200);
    expect(writes).toEqual(["confirm", "mail"]);
    const token = makeWaitlistToken(String(row!.verification_id), "leave", now);
    const response = await leave.POST(new Request(`https://cuadrao.example.test/api/waitlist/leave?token=${token}`, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: "List-Unsubscribe=One-Click" }));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "removed" });
    expect(row).toBeNull();
    expect(writes).toEqual(["confirm", "mail", "leave"]);
  } finally {
    globalThis.fetch = fetchBefore;
    for (const key of Object.keys(settings)) { if (before[key] === undefined) delete process.env[key]; else process.env[key] = before[key]; }
  }
});
