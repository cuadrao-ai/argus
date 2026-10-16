import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import { Webhook } from "standardwebhooks";
import { handleAuthEmailHook, type AuthDelivery } from "../server/emails/auth-hook";

const secret = Buffer.from("synthetic-hook-secret-not-a-live-key").toString("base64");
const config = {
  enabled: true,
  projectRef: "skedzwocnmrhfigiwyzi",
  supabaseUrl: "https://skedzwocnmrhfigiwyzi.supabase.co",
  appOrigin: "https://cuadrao-web-staging.onrender.com",
  expirySeconds: 3600,
  renderServiceId: "srv-db5ihr7lot8c73f3b3h0",
  hookSecret: secret,
};
const payload = (action = "recovery") => ({
  user: { email: "owner@example.test", new_email: "new@example.test" },
  email_data: {
    email_action_type: action,
    site_url: config.appOrigin,
    redirect_to: `${config.appOrigin}/auth/recovery`,
    token: "123456", token_new: "654321",
    token_hash: "a".repeat(64), token_hash_new: "b".repeat(64),
  },
});
function request(value: unknown, id = "test-webhook-id") {
  const body = JSON.stringify(value);
  const timestamp = new Date();
  return new Request("https://cuadrao-web-staging.onrender.com/api/auth/send-email", {
    method: "POST", headers: {
      "content-type": "application/json",
      "webhook-id": id,
      "webhook-timestamp": String(Math.floor(timestamp.getTime() / 1000)),
      "webhook-signature": new Webhook(secret).sign(id, timestamp, body),
    }, body,
  });
}

describe("staging Auth email hook", () => {
  test("is disabled by default and refuses mismatched project, origin or expiry without sending", async () => {
    for (const invalid of [
      { ...config, enabled: false },
      { ...config, projectRef: "different-project" },
      { ...config, supabaseUrl: "https://different-project.supabase.co" },
      { ...config, appOrigin: "https://example.test" },
      { ...config, expirySeconds: 60 },
    ]) {
      const sent: AuthDelivery[] = [];
      const response = await handleAuthEmailHook(request(payload()), invalid, async (email) => { sent.push(email); });
      assert.notEqual(response.status, 200);
      assert.equal((sent).length, 0);
    }
  });

  test("accepts Next internal URLs only in the pinned Render service, regardless of spoofed forwarding headers", async () => {
    const signed = request(payload());
    const body = await signed.text();
    const headers = new Headers(signed.headers);
    headers.set("host", "cuadrao-web-staging.onrender.com");
    headers.set("x-forwarded-host", "cuadrao-web-staging.onrender.com");
    headers.set("x-forwarded-proto", "https");
    const sent: AuthDelivery[] = [];
    const internal = new Request("http://0.0.0.0:10000/api/auth/send-email", { method: "POST", headers, body });
    assert.equal((await handleAuthEmailHook(internal, config, async (email) => { sent.push(email); })).status, 200);
    assert.equal(sent.length, 1);
    for (const renderServiceId of ["", "srv-other-service"]) {
      for (const url of [internal.url, signed.url]) {
        const candidate = new Request(url, { method: "POST", headers, body });
        const rejected: AuthDelivery[] = [];
        assert.equal((await handleAuthEmailHook(candidate, { ...config, renderServiceId }, async (email) => { rejected.push(email); })).status, 503);
        assert.equal(rejected.length, 0);
      }
    }
  });

  test("sends approved recovery with fixed sender headers and an exact staging Supabase verification link", async () => {
    const sent: AuthDelivery[] = [];
    const response = await handleAuthEmailHook(request(payload()), config, async (email) => { sent.push(email); });
    assert.equal(response.status, 200);
    assert.equal((sent).length, 1);
    assert.equal(sent[0].recipient, "owner@example.test");
    assert.equal(sent[0].from, "Cuadrao <hola@mail.cuadrao.ai>");
    assert.equal(sent[0].replyTo, "hola@cuadrao.ai");
    assert.equal(sent[0].subject, "Cambia tu contraseña de Cuadrao");
    assert.ok((sent[0].text).includes(`https://skedzwocnmrhfigiwyzi.supabase.co/auth/v1/verify?token=${"a".repeat(64)}&type=recovery&redirect_to=https%3A%2F%2Fcuadrao-web-staging.onrender.com%2Fauth%2Frecovery`));
    assert.ok((sent[0].text).includes("El enlace vence en 1 hora y solo se puede usar una vez."));
  });

  test("renders the approved Spanish copy and shared layout for each action", async () => {
    const cases = [
      ["signup", "123456 es tu código de Cuadrao", "Úsalo para confirmar tu cuenta."],
      ["invite", "Te invitaron a Cuadrao", "Te invitaron a usar Cuadrao."],
      ["magiclink", "Tu enlace para entrar", "Entra aquí."],
      ["reauthentication", "Tu código de verificación", "123456"],
    ];
    for (const [action, subject, body] of cases) {
      const sent: AuthDelivery[] = [];
      const response = await handleAuthEmailHook(request(payload(action)), config, async (email) => { sent.push(email); });
      assert.equal(response.status, 200);
      assert.equal((sent).length, 1);
      assert.equal(sent[0].subject, subject);
      assert.ok((sent[0].text).includes(body));
      assert.ok(sent[0].html.includes("Saludos, el equipo de Cuadrao"));
      assert.ok(!sent[0].html.includes("Salir de la lista"));
    }
  });

  test("secure email change sends both addresses with the official hash mapping and stable distinct retry keys", async () => {
    const accepted = new Map<string, AuthDelivery>();
    let failSecond = true;
    const sender = async (email: AuthDelivery) => {
      if (email.recipient === "new@example.test" && failSecond) throw new Error("synthetic delivery outage");
      accepted.set(email.idempotencyKey, email);
    };
    assert.equal((await handleAuthEmailHook(request(payload("email_change")), config, sender)).status, 503);
    assert.equal(accepted.size, 1);
    failSecond = false;
    assert.equal((await handleAuthEmailHook(request(payload("email_change")), config, sender)).status, 200);
    assert.equal(accepted.size, 2);
    const deliveries = [...accepted.values()];
    assert.equal(deliveries[0].recipient, "owner@example.test");
    assert.ok((deliveries[0].text).includes(`token=${"b".repeat(64)}`));
    assert.equal(deliveries[1].recipient, "new@example.test");
    assert.ok((deliveries[1].text).includes(`token=${"a".repeat(64)}`));
    for (const delivery of deliveries) {
      assert.equal(delivery.subject, "Confirma tu nuevo correo");
      assert.ok((delivery.text).includes("Confirma que quieres usar este correo en Cuadrao."));
    }
  });

  test("preserves PKCE token prefixes and Supabase empty-redirect defaults", async () => {
    const pkce = payload();
    pkce.email_data.token_hash = `pkce_${"c".repeat(64)}`;
    const sent: AuthDelivery[] = [];
    assert.equal((await handleAuthEmailHook(request(pkce), config, async (email) => { sent.push(email); })).status, 200);
    assert.ok((sent[0].text).includes(`token=pkce_${"c".repeat(64)}`));
    for (const action of ["signup", "invite", "magiclink", "recovery", "email_change", "reauthentication"]) {
      const empty = payload(action);
      empty.email_data.redirect_to = "";
      const emails: AuthDelivery[] = [];
      assert.equal((await handleAuthEmailHook(request(empty), config, async (email) => { emails.push(email); })).status, 200);
      assert.equal(emails.length, action === "email_change" ? 2 : 1);
      if (action !== "reauthentication") assert.ok((emails[0].text).includes("redirect_to="));
    }
  });

  test("rejects bad signatures, mutated raw bytes, stale signatures, unknown actions and unsafe recipient or redirect", async () => {
    const badSignature = request(payload());
    badSignature.headers.set("webhook-signature", "v1,invalid");
    const stale = request(payload());
    stale.headers.set("webhook-timestamp", "1");
    const mutated = request(payload());
    const mutatedBody = await mutated.text();
    const unsafeRecipient = payload();
    unsafeRecipient.user.email = "victim@example.test\r\nBcc: attacker@example.test";
    const unsafeRedirect = payload();
    unsafeRedirect.email_data.redirect_to = "https://example.test/auth/recovery";
    const wrongSite = payload();
    wrongSite.email_data.site_url = "https://example.test";
    const missingSecond = payload("email_change");
    missingSecond.email_data.token_hash_new = "";
    for (const candidate of [
      badSignature, stale,
      new Request(mutated.url, { method: "POST", headers: mutated.headers, body: `${mutatedBody} ` }),
      request(payload("password_changed_notification")),
      request(unsafeRecipient), request(unsafeRedirect), request(wrongSite), request(missingSecond),
      request({ private: "synthetic".repeat(10000) }),
    ]) {
      const sent: AuthDelivery[] = [];
      const response = await handleAuthEmailHook(candidate, config, async (email) => { sent.push(email); });
      assert.notEqual(response.status, 200);
      assert.equal((sent).length, 0);
      assert.ok(!(await response.text()).includes("synthetic"));
    }
  });
});
