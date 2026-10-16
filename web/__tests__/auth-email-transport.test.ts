import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import { resendAuthEmailSender } from "../server/emails/resend";
import { authEmailHookConfig } from "../server/emails/auth-hook";
import { renderAuthMail, type AuthMail } from "../server/emails/auth-actions";
const delivery = { recipient: "owner@example.test", from: "Cuadrao <hola@mail.cuadrao.ai>", replyTo: "hola@cuadrao.ai", subject: "subject", html: "<p>synthetic</p>", text: "synthetic", idempotencyKey: "auth-synthetic-key" };

describe("Auth email compatibility and delivery", () => {
  test("every account action uses the shared layout and only signup puts the code in its subject", async () => {
    const linked = { recipient: "owner@example.test", tokenHash: "a".repeat(64), redirectTo: "https://cuadrao-web-staging.onrender.com/" };
    const cases: AuthMail[] = [
      { ...linked, action: "signup", token: "55070219" },
      { ...linked, action: "invite" },
      { ...linked, action: "magiclink", token: "55070219" },
      { ...linked, action: "email_change", newEmail: "new@example.test" },
      { action: "reauthentication", recipient: linked.recipient, token: "55070219" },
    ];
    for (const mail of cases) {
      const rendered = await renderAuthMail(mail, "https://skedzwocnmrhfigiwyzi.supabase.co");
      assert.equal(rendered.subject.includes("55070219"), mail.action === "signup");
      assert.equal(rendered.text.includes("55070219"), ["signup", "magiclink", "reauthentication"].includes(mail.action));
      assert.ok(rendered.html.includes('alt="Cuadrao"'));
      assert.ok(rendered.html.includes("Saludos, el equipo de Cuadrao"));
      assert.ok(!rendered.html.includes("Salir de la lista"));
      if (mail.action !== "reauthentication") {
        assert.ok(rendered.text.includes(`type=${mail.action}&redirect_to=`));
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
