import { installEmailFixture } from "./helpers/email-fixture";
installEmailFixture();
import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { confirmAuthGet, type AuthConfirmType } from "../lib/auth-confirm";
import { parseAuthMail, renderAuthMail, type AuthMail } from "../server/emails/auth-actions";
import { buildDashboardAuthPaste } from "../server/emails/auth-paste";
import { renderAccountEmail } from "../server/emails/account-layout.generated";
import { createAuthSecurityActions, type AuthSecurityPort } from "../lib/auth-security";

const origin = "https://app.example.test";
const hash = "a".repeat(64);
const sentAt = new Date("2026-10-17T02:05:00Z");

function confirmRequest(query: string) {
  return new Request(`${origin}/auth/confirm?${query}`);
}

function verifier(result: { error: unknown } | "throw") {
  const calls: Array<{ token_hash: string; type: AuthConfirmType }> = [];
  const verify = async (input: { token_hash: string; type: AuthConfirmType }) => {
    calls.push(input);
    if (result === "throw") throw new Error("synthetic verify failure");
    return result;
  };
  return { calls, verify };
}

test("a valid token verifies and redirects only to the internal path", async () => {
  const { calls, verify } = verifier({ error: null });
  const response = await confirmAuthGet(
    confirmRequest(`token_hash=${hash}&type=recovery&next=/auth/recovery`),
    verify,
  );
  expect(response.status).toBe(303);
  expect(response.headers.get("cache-control")).toBe("no-store");
  expect(response.headers.get("location")).toBe(`${origin}/auth/recovery`);
  expect(calls).toEqual([{ token_hash: hash, type: "recovery" }]);
});

test("a same-origin absolute next is reduced to its path before redirect", async () => {
  const { calls, verify } = verifier({ error: null });
  const response = await confirmAuthGet(
    confirmRequest(`token_hash=${hash}&type=email&next=${encodeURIComponent(`${origin}/chat?idea=1`)}`),
    verify,
  );
  expect(response.headers.get("location")).toBe(`${origin}/chat?idea=1`);
  expect(calls).toEqual([{ token_hash: hash, type: "email" }]);
});

test("a missing next stays internal and a signup type is accepted", async () => {
  const recovery = verifier({ error: null });
  const recoveryResponse = await confirmAuthGet(confirmRequest(`token_hash=${hash}&type=recovery`), recovery.verify);
  expect(recoveryResponse.headers.get("location")).toBe(`${origin}/auth/recovery`);
  const signup = verifier({ error: null });
  const signupResponse = await confirmAuthGet(confirmRequest(`token_hash=pkce_${"c".repeat(64)}&type=signup`), signup.verify);
  expect(signupResponse.headers.get("location")).toBe(`${origin}/`);
  expect(signup.calls).toEqual([{ token_hash: `pkce_${"c".repeat(64)}`, type: "signup" }]);
});

test("an invalid token shows the confirm error and does not echo the hash", async () => {
  for (const result of [{ error: { message: "expired" } } as const, "throw" as const]) {
    const { calls, verify } = verifier(result);
    const response = await confirmAuthGet(
      confirmRequest(`token_hash=${hash}&type=email&next=/`),
      verify,
    );
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe(`${origin}/auth/confirm/error`);
    expect(response.headers.get("location")).not.toContain(hash);
    expect(calls).toHaveLength(1);
  }
  const malformed = verifier({ error: null });
  const response = await confirmAuthGet(confirmRequest("token_hash=short&type=email&next=/"), malformed.verify);
  expect(response.headers.get("location")).toBe(`${origin}/auth/confirm/error`);
  expect(malformed.calls).toHaveLength(0);
});

test("an external next is rejected before the token is verified", async () => {
  const blocked = [
    "https://evil.example/phish",
    "//evil.example",
    "/\\evil",
    "javascript:alert(1)",
    "https://app.example.test.evil.example/phish",
    "",
  ];
  for (const next of blocked) {
    const { calls, verify } = verifier({ error: null });
    const response = await confirmAuthGet(
      confirmRequest(`token_hash=${hash}&type=email&next=${encodeURIComponent(next)}`),
      verify,
    );
    expect(response.headers.get("location")).toBe(`${origin}/auth/confirm/error`);
    expect(calls).toHaveLength(0);
  }
});

test("the confirm route wires verifyOtp through the server client", () => {
  const source = readFileSync(new URL("../app/auth/confirm/route.ts", import.meta.url), "utf8");
  expect(source).toContain("createClient()");
  expect(source).toContain("verifyOtp");
  expect(source).toContain("confirmAuthGet");
});

const linked: AuthMail[] = [
  { action: "signup", recipient: "ada@example.test", tokenHash: hash, redirectTo: `${origin}/` },
  { action: "magiclink", recipient: "ada@example.test", tokenHash: hash, redirectTo: `${origin}/`, token: "55070219" },
  { action: "recovery", recipient: "ada@example.test", tokenHash: hash, redirectTo: `${origin}/auth/recovery` },
  { action: "invite", recipient: "ada@example.test", tokenHash: hash, redirectTo: `${origin}/` },
  { action: "email_change", audience: "new_address", recipient: "new@example.test", tokenHash: hash, redirectTo: `${origin}/`, newEmail: "new@example.test" },
  { action: "reauthentication", recipient: "ada@example.test", token: "55070219" },
];

function assertPlainUrls(text: string) {
  for (const line of text.split("\n")) {
    if (!line.includes("https://") && !line.includes("{{ .SiteURL }}")) continue;
    expect(line).toMatch(/^(?:https:\/\/\S+|\{\{ \.SiteURL \}\}\/auth\/confirm\?token_hash=\{\{ \.TokenHash \}\}&type=\w+&next=\/\S*)$/);
    expect(line).not.toMatch(/[.,;:!?)>\]]$|%2E$/);
  }
}

test("rendered auth links stay on the app confirm route with no trailing punctuation", async () => {
  for (const mail of linked) {
    const rendered = await renderAuthMail(mail, origin, 3600, sentAt);
    expect(`${rendered.subject}\n${rendered.html}\n${rendered.text}`).not.toContain("supabase.co");
    expect(rendered.html).not.toContain("/auth/v1/verify");
    assertPlainUrls(rendered.text);
    if (mail.action !== "reauthentication") {
      expect(rendered.text).toContain("/auth/confirm?token_hash=");
      expect(rendered.html).toContain("/auth/confirm?token_hash=");
    }
  }
});

test("signup confirmation is link-only with the approved subject", async () => {
  const rendered = await renderAuthMail(linked[0], origin, 3600, sentAt);
  expect(rendered.subject).toBe("Confirma tu correo en Cuadrao");
  expect(rendered.subject).not.toMatch(/\d/);
  expect(rendered.text).not.toMatch(/\b\d{6,10}\b/);
  expect(rendered.html).not.toContain('class="code"');
  expect(rendered.text).not.toContain("código");
  expect(rendered.text).toContain("type=email");
  expect(rendered.text).toContain("Confirmar mi cuenta");
  const parsed = parseAuthMail({
    user: { email: "ada@example.test" },
    email_data: {
      email_action_type: "signup",
      site_url: origin,
      redirect_to: `${origin}/`,
      token: "55070219",
      token_hash: hash,
    },
  }, origin);
  expect(parsed).toEqual([{ action: "signup", recipient: "ada@example.test", tokenHash: hash, redirectTo: `${origin}/` }]);
});

test("dashboard paste uses token_hash placeholders and the approved subjects", async () => {
  const records = await buildDashboardAuthPaste();
  const byFile = Object.fromEntries(records.map((record) => [record.file, record]));
  expect(byFile.confirmation.subjectField).toBe("mailer_subjects_confirmation");
  expect(byFile.confirmation.bodyField).toBe("mailer_templates_confirmation_content");
  expect(byFile.confirmation.subject).toBe("Confirma tu correo en Cuadrao");
  expect(byFile.confirmation.text).toContain("{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=email&next=/");
  expect(byFile.confirmation.html).toContain("{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&amp;type=email&amp;next=/");
  expect(byFile.confirmation.text).not.toContain("{{ .Token }}");
  expect(byFile.magic_link.subjectField).toBe("mailer_subjects_magic_link");
  expect(byFile.magic_link.subject).toBe("{{ .Token }} es tu código para entrar a Cuadrao");
  expect(byFile.magic_link.text).toContain("type=magiclink&next=/");
  expect(byFile.recovery.subjectField).toBe("mailer_subjects_recovery");
  expect(byFile.recovery.bodyField).toBe("mailer_templates_recovery_content");
  expect(byFile.recovery.subject).toBe("Cambio de contraseña en Cuadrao");
  expect(byFile.recovery.text).toContain("type=recovery&next=/auth/recovery");
  expect(byFile.invite.subjectField).toBe("mailer_subjects_invite");
  expect(byFile.invite.bodyField).toBe("mailer_templates_invite_content");
  expect(byFile.invite.subject).toBe("Te invitaron a Cuadrao");
  expect(byFile.invite.text).toContain("type=invite&next=/");
  expect(byFile.email_change.subjectField).toBe("mailer_subjects_email_change");
  expect(byFile.email_change.bodyField).toBe("mailer_templates_email_change_content");
  expect(byFile.email_change.subject).toBe("Confirma tu nuevo correo");
  expect(byFile.email_change.text).toContain("type=email_change&next=/");
  expect(byFile.reauthentication.subjectField).toBe("mailer_subjects_reauthentication");
  expect(byFile.reauthentication.bodyField).toBe("mailer_templates_reauthentication_content");
  expect(byFile.reauthentication.subject).toBe("{{ .Token }} es tu código de verificación de Cuadrao");
  for (const record of records) {
    expect(`${record.subject}\n${record.html}\n${record.text}`).not.toContain("supabase.co");
    expect(record.text).not.toContain(hash);
    expect(record.html).not.toContain(hash);
    assertPlainUrls(record.text);
    if (record.file === "confirmation") {
      expect(record.subject).not.toMatch(/\d/);
      expect(record.text).not.toMatch(/\b\d{6,10}\b/);
      expect(record.html).not.toContain('class="code"');
    }
  }
});

test("the layout accepts the confirm template and still rejects other links and codes", () => {
  const template = "{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=email&next=/";
  const rendered = renderAccountEmail({
    title: "Confirma tu correo en Cuadrao",
    paragraphs: ["Confirma tu correo desde este enlace:"],
    action: { label: "Confirmar mi cuenta", url: template },
    code: "{{ .Token }}",
  });
  expect(rendered.text.split("\n")).toContain(template);
  expect(rendered.text).toContain("{{ .Token }}");
  expect(rendered.html).toContain(template.replaceAll("&", "&amp;"));
  expect(() => renderAccountEmail({
    title: "Confirma tu correo en Cuadrao",
    paragraphs: [],
    action: { label: "Confirmar mi cuenta", url: "javascript:alert(1)" },
  })).toThrow();
  expect(() => renderAccountEmail({
    title: "Confirma tu correo en Cuadrao",
    paragraphs: [],
    code: "not-a-code",
  })).toThrow();
});

test("the check-your-email screen uses the approved sentence", () => {
  const es = JSON.parse(readFileSync(new URL("../public/locales/es-419/common.json", import.meta.url), "utf8"));
  const en = JSON.parse(readFileSync(new URL("../public/locales/en/common.json", import.meta.url), "utf8"));
  expect(es.auth.signup.confirmation_description).toBe("Abre el enlace que te enviamos y entrarás directo a Cuadrao.");
  expect(en.auth.signup.confirmation_description).toBe("Open the link we sent and you'll go straight into Cuadrao.");
  const form = readFileSync(new URL("../components/auth/AuthForm.tsx", import.meta.url), "utf8");
  expect(form).toContain("Open the link we sent and you'll go straight into Cuadrao.");
});

test("a recovery page with a session and no code is ready", async () => {
  const port: AuthSecurityPort = {
    async exchangeCodeForSession() {
      return { error: null };
    },
    async updateUser() {
      return { error: null };
    },
    async signOut() {
      return { error: null };
    },
  };
  const absent = createAuthSecurityActions(port, async () => undefined);
  expect(await absent.hasRecoverySession()).toBe(false);
  const ready = createAuthSecurityActions({ ...port, hasSession: async () => true }, async () => undefined);
  expect(await ready.hasRecoverySession()).toBe(true);
  const failed = createAuthSecurityActions({
    ...port,
    hasSession: async () => {
      throw new Error("synthetic session read failure");
    },
  }, async () => undefined);
  expect(await failed.hasRecoverySession()).toBe(false);
  const page = readFileSync(new URL("../app/auth/recovery/page.tsx", import.meta.url), "utf8");
  const codeRead = page.indexOf('.get("code")');
  const queryRemoved = page.indexOf('window.history.replaceState(null, "", "/auth/recovery")');
  const session = page.indexOf("hasRecoverySession()");
  const exchange = page.indexOf(".exchangeRecoveryCode(code)");
  expect(session).toBeGreaterThan(queryRemoved);
  expect(exchange).toBeGreaterThan(queryRemoved);
  expect(queryRemoved).toBeGreaterThan(codeRead);
});
