import { installEmailFixture } from "./helpers/email-fixture";
installEmailFixture();
import assert from "node:assert/strict";
import { describe, test, setSystemTime } from "bun:test";
import { Webhook } from "standardwebhooks";
import { resendAuthEmailSender } from "../server/emails/resend";
import { authEmailHookConfig, handleAuthEmailHook, STAGING_AUTH_EMAIL } from "../server/emails/auth-hook";
import { renderAuthMail, type AuthMail } from "../server/emails/auth-actions";
const delivery = { recipient: "owner@example.test", from: "Cuadrao <hola@mail.cuadrao.ai>", replyTo: "hola@cuadrao.ai", subject: "subject", html: "<p>synthetic</p>", text: "synthetic", idempotencyKey: "auth-synthetic-key" };

describe("Auth email compatibility and delivery", () => {
  test("every account action uses the shared layout and all code emails put the code first in the subject", async () => {
    const linked = { recipient: "owner@example.test", tokenHash: "a".repeat(64), redirectTo: "https://cuadrao-web-staging.onrender.com/" };
    const cases: AuthMail[] = [
      { ...linked, action: "signup", token: "55070219" },
      { ...linked, action: "magiclink", token: "55070219" },
      { ...linked, action: "invite" },
      { ...linked, action: "email_change", audience: "old_address", newEmail: "new@example.test" },
      { ...linked, action: "email_change", audience: "new_address", recipient: "new@example.test", newEmail: "new@example.test" },
      { action: "reauthentication", recipient: linked.recipient, token: "55070219" },
    ];
    for (const mail of cases) {
      const rendered = await renderAuthMail(mail, "https://app.example.test", 3600);
      const carriesCode = mail.action === "signup" || mail.action === "magiclink" || mail.action === "reauthentication";
      assert.equal(rendered.subject.startsWith("55070219 "), carriesCode);
      assert.equal(rendered.text.includes("55070219"), carriesCode);
      assert.ok(rendered.html.includes('alt="Cuadrao"'));
      assert.ok(rendered.html.includes("Saludos,<br>Cuadrao"));
      assert.ok(!rendered.html.includes("Salir de la lista"));
      assert.ok(rendered.text.includes("Cuadrao LLC"));
      assert.ok(!rendered.text.includes("Cuadrao LLC,"));
      if (mail.action === "signup" || mail.action === "magiclink") {
        assert.equal(/https?:\/\//.test(rendered.text), false);
        assert.equal(rendered.html.includes('href="https:'), false);
        assert.ok(!rendered.text.includes("/auth/"));
      }
      if (mail.action === "invite" || mail.action === "email_change") {
        assert.ok(rendered.text.includes("https://app.example.test/auth/confirm?token_hash="));
        assert.ok(rendered.text.includes(`type=${mail.action}`));
        assert.ok(!rendered.text.includes("supabase.co"));
        assert.ok(!rendered.text.includes("redirect_to="));
      }
    }
  });

  test("posts both rendered parts and the same per-recipient key on repeat without retries", async () => {
    const requests: Request[] = [];
    const sender = resendAuthEmailSender("synthetic-api-key", async (url, options) => {
      requests.push(new Request(url, options));
      return Response.json({ id: "synthetic-delivery-id" });
    });
    await sender(delivery);
    await sender(delivery);
    assert.equal((requests).length, 2);
    for (const request of requests) {
      assert.equal(request.url, "https://api.resend.com/emails");
      assert.equal(request.headers.get("Idempotency-Key"), delivery.idempotencyKey);
      assert.deepEqual(await request.json(), { from: delivery.from, reply_to: delivery.replyTo, to: [delivery.recipient], subject: delivery.subject, html: delivery.html, text: delivery.text });
    }
    const failed: Request[] = [];
    const refusing = resendAuthEmailSender("synthetic-api-key", async (url, options) => {
      failed.push(new Request(url, options));
      return Response.json({ private: "provider-secret-detail" }, { status: 429 });
    });
    await assert.rejects(refusing(delivery), new RegExp("Auth email provider unavailable"));
    assert.equal((failed).length, 1);
  });

  test("missing credentials make no provider request and default configuration is off", async () => {
    let calls = 0;
    const sender = resendAuthEmailSender(undefined, async () => { calls++; return Response.json({}); });
    await assert.rejects(sender(delivery), new RegExp("Auth email provider unavailable"));
    assert.equal(calls, 0);
    assert.equal(authEmailHookConfig({}).enabled, false);
    assert.equal(authEmailHookConfig({}).renderServiceId, "");
    assert.equal(authEmailHookConfig({ RENDER_SERVICE_ID: "srv-db5ihr7lot8c73f3b3h0" }).renderServiceId, "srv-db5ihr7lot8c73f3b3h0");
  });
});

for (const action of ["password_changed_notification", "email_changed_notification"]) {
  for (const failure of ["accepted-response-lost", "rejected-before-acceptance"]) {
    test(`${action} retries ${failure} across a minute with identical provider content`, async () => {
      const secret = Buffer.from("local-review-synthetic-secret").toString("base64");
      const config = { ...STAGING_AUTH_EMAIL, enabled: true, hookSecret: secret };
      const timestamp = new Date("2026-10-17T12:00:59Z");
      const id = `recipient-synthetic-${action}`;
      const body = JSON.stringify({
        user: { email: "new@example.test" },
        email_data: { email_action_type: action, old_email: "old@example.test", site_url: config.appOrigin, redirect_to: "" },
      });
      const request = () => new Request("http://localhost/api/auth/send-email", {
        method: "POST", body, headers: {
          "content-type": "application/json", "webhook-id": id,
          "webhook-timestamp": String(timestamp.getTime() / 1000),
          "webhook-signature": new Webhook(secret).sign(id, timestamp, body),
        },
      });
      const accepted = new Map<string, string>();
      const requests: string[] = [];
      let conflicts = 0;
      const provider: typeof fetch = async (_url, options) => {
        const key = new Headers(options?.headers).get("Idempotency-Key")!;
        const content = String(options?.body);
        requests.push(content);
        if (accepted.has(key) && accepted.get(key) !== content) {
          conflicts++;
          return Response.json({ name: "invalid_idempotent_request" }, { status: 409 });
        }
        if (requests.length === 1 && failure === "rejected-before-acceptance") {
          return Response.json({ name: "rate_limit" }, { status: 429 });
        }
        accepted.set(key, content);
        if (requests.length === 1) throw new Error("accepted; response lost");
        return Response.json({ id: "synthetic" });
      };
      try {
        setSystemTime(timestamp);
        const first = await handleAuthEmailHook(request(), config, resendAuthEmailSender("synthetic", provider));
        setSystemTime(new Date(timestamp.getTime() + 2_000));
        const retry = await handleAuthEmailHook(request(), config, resendAuthEmailSender("synthetic", provider));
        assert.equal(first.status, 503);
        assert.equal(retry.status, 200);
        assert.equal(conflicts, 0);
        assert.equal(accepted.size, 1);
        assert.equal(requests.length, 2);
        assert.ok(requests[0] === requests[1], "provider payload changed on retry");
      } finally { setSystemTime(); }
    });
  }
}
