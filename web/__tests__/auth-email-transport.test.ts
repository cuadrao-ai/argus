import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import { resendAuthEmailSender } from "../server/emails/resend";
import { authEmailHookConfig } from "../server/emails/auth-hook";
import { renderAuthMail, type AuthMail } from "../server/emails/auth-actions";
import existing from "./fixtures/auth-email-existing-templates.json";

const delivery = { recipient: "owner@example.test", from: "Cuadrao <hola@mail.cuadrao.ai>", replyTo: "hola@cuadrao.ai", subject: "subject", html: "<p>synthetic</p>", text: "synthetic", idempotencyKey: "auth-synthetic-key" };
const normalize = (html: string) => html.replaceAll("&#x27;", "'").replaceAll("&#39;", "'").replace(/<!--[^]*?-->/g, "").replace(/^<!doctype[^>]*>/i, "").replace(/>\s+</g, "><").trim();

describe("Auth email compatibility and delivery", () => {
  test("retains the complete captured body and subject for every non-recovery action", async () => {
    const linked = { recipient: "owner@example.test", tokenHash: "a".repeat(64), redirectTo: "https://cuadrao-web-staging.onrender.com/" };
    const cases: Array<{ key: keyof typeof existing; mail: AuthMail }> = [
      { key: "confirmation", mail: { ...linked, action: "signup" } },
      { key: "invite", mail: { ...linked, action: "invite" } },
      { key: "magic_link", mail: { ...linked, action: "magiclink" } },
      { key: "email_change", mail: { ...linked, action: "email_change", newEmail: "new@example.test" } },
      { key: "reauthentication", mail: { action: "reauthentication", recipient: linked.recipient, token: "123456" } },
    ];
    for (const { key, mail } of cases) {
      const rendered = await renderAuthMail(mail, "https://skedzwocnmrhfigiwyzi.supabase.co");
      const expectedUrl = `https://skedzwocnmrhfigiwyzi.supabase.co/auth/v1/verify?token=${linked.tokenHash}&type=${mail.action}&redirect_to=https%3A%2F%2Fcuadrao-web-staging.onrender.com%2F`;
      const body = existing[key].body.replaceAll("{{ .ConfirmationURL }}", expectedUrl.replaceAll("&", "&amp;")).replaceAll("{{ .NewEmail }}", "new@example.test").replaceAll("{{ .Token }}", "123456");
      assert.equal(normalize(rendered.html), normalize(body));
      assert.equal(rendered.subject, existing[key].subject.replaceAll("{{ .Token }}", "123456"));
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
