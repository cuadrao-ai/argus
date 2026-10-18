import { expect, test } from "bun:test";
import { waitlistMail } from "../lib/waitlist/email";
import { waitlistDeps } from "../lib/waitlist/runtime";
import type { WaitlistRow } from "../lib/waitlist/types";
const row: WaitlistRow = { email: "fixture@example.test", email_digest: "cd".repeat(32), verification_id: "ab".repeat(32), created_at: "2026-10-16T12:00:00Z", confirmed_at: "2026-10-16T13:00:00Z", last_confirmation_sent_at: "2026-10-16T12:00:00Z", reminder_sent_at: null, privacy_policy_version: "2026-10-16" };
const config = { apiKey: "fixture-key", apiUrl: "https://provider.example.test", origin: "https://cuadrao.example.test", from: "Cuadrao <lista@cuadrao.ai>", postalAddress: "Cuadrao LLC, 1209 Mountain Road Pl NE Ste N, Albuquerque NM 87110, EE. UU." };

test("all automatic mail uses the shared layout, leave headers, address and reply mailbox", async () => {
  const payloads: Record<string, unknown>[] = [];
  const send = waitlistMail(config, (async (_url, init) => { payloads.push(JSON.parse(String(init?.body))); return Response.json({ id: "fixture" }); }) as typeof fetch);
  for (const kind of ["confirmation", "reminder", "welcome"] as const) expect(await send(kind, row)).toBe("sent");
  for (const body of payloads) {
    expect(body.from).toBe(config.from); expect(body.reply_to).toBe("hola@cuadrao.ai");
    expect(body.html).toContain(config.postalAddress);
    expect(body.html).toContain("Saludos, el equipo de Cuadrao");
    expect(body.html).toContain("Salir de la lista");
    expect(body.html).not.toContain('class="code"');
    expect(body.html).not.toContain("¿Buscas Cuadrao para tu negocio?");
    expect(body.html).not.toContain(row.verification_id);
    expect(body.headers).toHaveProperty("List-Unsubscribe-Post", "List-Unsubscribe=One-Click");
  }
  expect(payloads[0].text).toContain("Confirmar mi correo");
  expect(payloads[0].text).toContain("Este enlace vence en 48 horas.");
  expect(payloads[2].text).not.toContain("Confirmar mi correo");
});

test("unknown provider outcome retries with the exact same body and key", async () => {
  const requests: RequestInit[] = [];
  const send = waitlistMail(config, (async (_url, init) => {
    requests.push(init!); if (requests.length === 1) throw new Error("timeout");
    return Response.json({ id: "fixture" });
  }) as typeof fetch);
  expect(await send("confirmation", row)).toBe("sent");
  expect(requests).toHaveLength(2); expect(requests[0]).toEqual(requests[1]);
});

test("provider refusal returns failure without another send", async () => {
  let attempts = 0;
  const send = waitlistMail(config, (async () => { attempts += 1; return new Response(null, { status: 403 }); }) as typeof fetch);
  expect(await send("reminder", row)).toBe("refused"); expect(attempts).toBe(1);
});

test("runtime fails closed for missing settings, wrong sender domain or non-HTTPS origin", () => {
  const env = { SUPABASE_URL: "https://staging.example.test", SUPABASE_SERVICE_ROLE_KEY: "fixture", RESEND_API_KEY: "fixture", MARKETING_WAITLIST_FROM: config.from, MARKETING_POSTAL_ADDRESS: config.postalAddress, CUADRAO_WAITLIST_ORIGIN: config.origin, CUADRAO_WAITLIST_TURNSTILE_SECRET: "fixture" };
  expect(waitlistDeps(env)).not.toBeNull();
  for (const name of Object.keys(env)) expect(waitlistDeps({ ...env, [name]: "" })).toBeNull();
  expect(waitlistDeps({ ...env, MARKETING_WAITLIST_FROM: "Cuadrao <fixture@other.example.test>" })).toBeNull();
  expect(waitlistDeps({ ...env, CUADRAO_WAITLIST_ORIGIN: "http://cuadrao.example.test" })).toBeNull();
});

test("a refusal after a lost response cannot release a possibly sent reservation", async () => {
  let attempts = 0;
  const send = waitlistMail(config, (async () => {
    attempts += 1;
    if (attempts === 1) throw new Error("timeout");
    return new Response(null, { status: 403 });
  }) as typeof fetch);
  expect(await send("confirmation", row)).toBe("unknown");
});


test("runtime allows only the approved subdomain sender on staging", () => {
  const env = { SUPABASE_URL: "https://skedzwocnmrhfigiwyzi.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "fixture", RESEND_API_KEY: "fixture", MARKETING_WAITLIST_FROM: "Cuadrao <no-responder@mail.cuadrao.ai>", MARKETING_POSTAL_ADDRESS: config.postalAddress, CUADRAO_WAITLIST_ORIGIN: config.origin, CUADRAO_WAITLIST_TURNSTILE_SECRET: "fixture" };
  expect(waitlistDeps(env)).not.toBeNull();
  expect(waitlistDeps({ ...env, SUPABASE_URL: "https://other-project.supabase.co" })).toBeNull();
  for (const from of ["Cuadrao <other@mail.cuadrao.ai>", "Cuadrao <no-responder@other.cuadrao.ai>", "Cuadrao <no-responder@mail.cuadrao.ai.example.test>", "Other <no-responder@mail.cuadrao.ai>"]) {
    expect(waitlistDeps({ ...env, MARKETING_WAITLIST_FROM: from })).toBeNull();
  }
});
