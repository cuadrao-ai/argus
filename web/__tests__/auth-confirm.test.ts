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
  { action: "recovery", recipient: "ada@example.test", tokenHash: hash, redirectTo: `${origin}/auth/recovery` },
  { action: "email_change", audience: "new_address", recipient: "new@example.test", tokenHash: hash, redirectTo: `${origin}/`, newEmail: "new@example.test" },
];

function assertPlainUrls(text: string) {
  for (const line of text.split("\n")) {
    if (!line.includes("https://") && !line.includes("{{ .SiteURL }}")) continue;
    expect(line).toMatch(/^(?:https:\/\/\S+|\{\{ \.SiteURL \}\}\/auth\/confirm\?token_hash=\{\{ \.TokenHash \}\}&type=\w+&next=\/\S*)$/);
    expect(line).not.toMatch(/[.,;:!?)>\]]$|%2E$/);
  }
}

test("recovery and email change stay on the app confirm route with no trailing punctuation", async () => {
  for (const mail of linked) {
    const rendered = await renderAuthMail(mail, origin, 3600, sentAt);
    expect(`${rendered.subject}\n${rendered.html}\n${rendered.text}`).not.toContain("supabase.co");
    expect(rendered.html).not.toContain("/auth/v1/verify");
    assertPlainUrls(rendered.text);
    expect(rendered.text).toContain("/auth/confirm?token_hash=");
    expect(rendered.html).toContain("/auth/confirm?token_hash=");
  }
});

test("signup and magic link keep the code and the provider verify link", async () => {
  const signup = await renderAuthMail(
    { action: "signup", recipient: "ada@example.test", tokenHash: hash, redirectTo: `${origin}/`, token: "55070219" },
    "https://project-ref.supabase.co",
    3600,
    sentAt,
  );
  expect(signup.subject).toBe("55070219 es tu código de Cuadrao");
  expect(signup.text).toContain("55070219");
  expect(signup.html).toContain('class="code"');
  expect(signup.text.split("\n")).toContain(
    `https://project-ref.supabase.co/auth/v1/verify?token=${hash}&type=signup&redirect_to=${encodeURIComponent(`${origin}/`)}`,
  );
  expect(signup.text).not.toContain("/auth/confirm");
  const magic = await renderAuthMail(
    { action: "magiclink", recipient: "ada@example.test", tokenHash: hash, redirectTo: `${origin}/`, token: "55070219" },
    "https://project-ref.supabase.co",
    3600,
    sentAt,
  );
  expect(magic.subject).toBe("55070219 es tu código para entrar a Cuadrao");
  expect(magic.text.split("\n")).toContain(
    `https://project-ref.supabase.co/auth/v1/verify?token=${hash}&type=magiclink&redirect_to=${encodeURIComponent(`${origin}/`)}`,
  );
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
  expect(parsed).toEqual([{ action: "signup", recipient: "ada@example.test", tokenHash: hash, redirectTo: `${origin}/`, token: "55070219" }]);
  expect(() => parseAuthMail({
    user: { email: "ada@example.test" },
    email_data: {
      email_action_type: "invite",
      site_url: origin,
      redirect_to: `${origin}/`,
      token_hash: hash,
    },
  }, origin)).toThrow();
});

test("dashboard paste wires recovery and email change only", async () => {
  const records = await buildDashboardAuthPaste();
  expect(records.map((record) => record.file)).toEqual(["recovery", "email_change"]);
  const byFile = Object.fromEntries(records.map((record) => [record.file, record]));
  expect(byFile.recovery.subjectField).toBe("mailer_subjects_recovery");
  expect(byFile.recovery.bodyField).toBe("mailer_templates_recovery_content");
  expect(byFile.recovery.subject).toBe("Cambio de contraseña en Cuadrao");
  expect(byFile.recovery.text.split("\n")).toContain("{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=recovery&next=/auth/recovery");
  expect(byFile.recovery.html).toContain("{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&amp;type=recovery&amp;next=/auth/recovery");
  expect(byFile.email_change.subjectField).toBe("mailer_subjects_email_change");
  expect(byFile.email_change.bodyField).toBe("mailer_templates_email_change_content");
  expect(byFile.email_change.subject).toBe("Confirma tu nuevo correo");
  expect(byFile.email_change.text.split("\n")).toContain("{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=email_change&next=/");
  for (const record of records) {
    expect(`${record.subject}\n${record.html}\n${record.text}`).not.toContain("supabase.co");
    expect(record.text).not.toContain(hash);
    expect(record.html).not.toContain(hash);
    assertPlainUrls(record.text);
  }
});

test("the layout accepts the confirm template and still rejects other links and codes", () => {
  const template = "{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=recovery&next=/auth/recovery";
  const rendered = renderAccountEmail({
    title: "Cambio de contraseña en Cuadrao",
    paragraphs: ["Elige una contraseña nueva desde este enlace:"],
    action: { label: "Elegir una contraseña nueva", url: template },
  });
  expect(rendered.text.split("\n")).toContain(template);
  expect(rendered.html).toContain(template.replaceAll("&", "&amp;"));
  expect(() => renderAccountEmail({
    title: "Cambio de contraseña en Cuadrao",
    paragraphs: [],
    action: { label: "Elegir una contraseña nueva", url: "javascript:alert(1)" },
  })).toThrow();
  expect(() => renderAccountEmail({
    title: "Cambio de contraseña en Cuadrao",
    paragraphs: [],
    code: "{{ .Token }}",
  })).toThrow();
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
