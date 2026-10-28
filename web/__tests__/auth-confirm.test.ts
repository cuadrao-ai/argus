import { installEmailFixture } from "./helpers/email-fixture";
installEmailFixture();
import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { confirmAuthGet, type AuthConfirmType } from "../lib/auth-confirm";
import { parseAuthMail, renderAuthMail, type AuthMail } from "../server/emails/auth-actions";
import { buildDashboardAuthPaste } from "../server/emails/auth-paste";
import { renderAccountEmail } from "../server/emails/account-layout.generated";
import { createAuthSecurityActions, type AuthSecurityPort } from "../lib/auth-security";
import { recoveryProof } from "../lib/recovery-proof";

const origin = "https://app.example.test";
const hash = "a".repeat(64);
const sentAt = new Date("2026-10-17T02:05:00Z");

function confirmRequest(query: string) {
  return new Request(`${origin}/auth/confirm?${query}`);
}

const accessToken = `h.${Buffer.from(JSON.stringify({ sub: "person-1", session_id: "session-1" })).toString("base64url")}.s`;
const session = { access_token: accessToken, user: { id: "person-1" } };

function verifier(result: { error: unknown } | "throw") {
  const calls: Array<{ token_hash: string; type: AuthConfirmType }> = [];
  const refusals: Array<{ reference: string; type: string | null; code: string }> = [];
  const verify = async (input: { token_hash: string; type: AuthConfirmType }) => {
    calls.push(input);
    if (result === "throw") throw new Error("synthetic verify failure");
    return result.error ? result : { error: null, data: { session } };
  };
  const report = (refusal: { reference: string; type: string | null; code: string }) => { refusals.push(refusal); };
  return { calls, refusals, verify, report };
}

function refusal(location: string | null) {
  const url = new URL(location ?? "", origin);
  return { path: url.pathname, code: url.searchParams.get("error_code"), type: url.searchParams.get("type"), ref: url.searchParams.get("ref"), hash: url.hash };
}

test("a valid token verifies and redirects only to the internal path", async () => {
  const { calls, verify } = verifier({ error: null });
  const response = await confirmAuthGet(
    confirmRequest(`token_hash=${hash}&type=recovery&next=/auth/recovery`),
    verify,
  );
  expect(response.status).toBe(303);
  expect(response.headers.get("cache-control")).toBe("no-store");
  const proof = await recoveryProof("person-1", "session-1");
  expect(response.headers.get("location")).toBe(`/auth/recovery#recovery_proof=${proof}`);
  expect(calls).toEqual([{ token_hash: hash, type: "recovery" }]);
});

test("the proof a confirm redirect carries opens the recovery form in that browser and survives reload", async () => {
  const { verify } = verifier({ error: null });
  const response = await confirmAuthGet(confirmRequest(`token_hash=${hash}&type=recovery`), verify);
  const handedOver = new URLSearchParams(new URL(response.headers.get("location") ?? "", origin).hash.slice(1)).get("recovery_proof") ?? "";
  const port: AuthSecurityPort = {
    async exchangeCodeForSession() { return { data: { redirectType: "recovery" }, error: null }; },
    async updateUser() { return { error: null }; },
    async signOut() { return { error: null }; },
    async getValidatedSession() { return { userId: "person-1", sessionId: "session-1" }; },
  };
  const values = new Map<string, string>();
  const store = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
  const landing = createAuthSecurityActions(port, async () => undefined, store);
  expect(await landing.hasRecoverySession()).toBe(false);
  await landing.acceptRecoveryProof(handedOver);
  expect(await landing.hasRecoverySession()).toBe(true);
  expect(await createAuthSecurityActions(port, async () => undefined, store).hasRecoverySession()).toBe(true);
  const ordinary = createAuthSecurityActions({ ...port, getValidatedSession: async () => ({ userId: "person-1", sessionId: "password-session" }) }, async () => undefined, store);
  expect(await ordinary.hasRecoverySession()).toBe(false);
  expect(ordinary.acceptRecoveryProof(handedOver)).rejects.toThrow();
});

test("a same-origin absolute next is reduced to its path before redirect", async () => {
  const { calls, verify } = verifier({ error: null });
  const response = await confirmAuthGet(
    confirmRequest(`token_hash=${hash}&type=email&next=${encodeURIComponent(`${origin}/chat?idea=1`)}`),
    verify,
  );
  expect(response.headers.get("location")).toBe("/chat?idea=1");
  expect(calls).toEqual([{ token_hash: hash, type: "email" }]);
});

test("a missing next stays internal and a signup type is accepted", async () => {
  const recovery = verifier({ error: null });
  const recoveryResponse = await confirmAuthGet(confirmRequest(`token_hash=${hash}&type=recovery`), recovery.verify);
  expect(recoveryResponse.headers.get("location")).toStartWith("/auth/recovery#recovery_proof=");
  const signup = verifier({ error: null });
  const signupResponse = await confirmAuthGet(confirmRequest(`token_hash=pkce_${"c".repeat(64)}&type=signup`), signup.verify);
  expect(signupResponse.headers.get("location")).toBe("/");
  expect(signup.calls).toEqual([{ token_hash: `pkce_${"c".repeat(64)}`, type: "signup" }]);
});

test("a refused token names the provider code, logs a reference, and does not echo the hash", async () => {
  const expired = verifier({ error: { code: "otp_expired", status: 403, message: "Email link is invalid or has expired" } });
  const response = await confirmAuthGet(confirmRequest(`token_hash=${hash}&type=email&next=/`), expired.verify, expired.report);
  expect(response.status).toBe(303);
  const seen = refusal(response.headers.get("location"));
  expect(seen).toMatchObject({ path: "/auth/confirm/error", code: "otp_expired", type: "email", hash: "" });
  expect(seen.ref).toMatch(/^[A-Za-z0-9_-]{4,64}$/);
  expect(expired.refusals).toEqual([{ reference: seen.ref, type: "email", code: "otp_expired" }]);
  expect(response.headers.get("location")).not.toContain(hash);
  expect(expired.calls).toHaveLength(1);

  for (const result of [{ error: { message: "no code" } } as const, "throw" as const]) {
    const { calls, verify, report } = verifier(result);
    const failed = await confirmAuthGet(confirmRequest(`token_hash=${hash}&type=email&next=/`), verify, report);
    expect(refusal(failed.headers.get("location"))).toMatchObject({ code: "verify_failed", type: "email" });
    expect(calls).toHaveLength(1);
  }

  const malformed = verifier({ error: null });
  const short = await confirmAuthGet(confirmRequest("token_hash=short&type=email&next=/"), malformed.verify, malformed.report);
  expect(refusal(short.headers.get("location"))).toMatchObject({ code: "malformed_link", type: "email" });
  expect(malformed.calls).toHaveLength(0);
  expect(malformed.refusals[0]?.code).toBe("malformed_link");
});

test("a recovery verify that returns no session is refused, never handed over", async () => {
  const calls: unknown[] = [];
  const response = await confirmAuthGet(
    confirmRequest(`token_hash=${hash}&type=recovery`),
    async (input) => { calls.push(input); return { error: null, data: { session: null } }; },
    () => undefined,
  );
  expect(refusal(response.headers.get("location"))).toMatchObject({ code: "verify_failed", type: "recovery", hash: "" });
  expect(calls).toHaveLength(1);
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
    expect(refusal(response.headers.get("location"))).toMatchObject({ path: "/auth/confirm/error", code: "malformed_link", type: "email" });
    expect(response.headers.get("location")).not.toContain("evil.example");
    expect(calls).toHaveLength(0);
  }
});

test("a localhost bind origin never appears in the redirect", async () => {
  const success = verifier({ error: null });
  const response = await confirmAuthGet(
    new Request(`http://localhost:10000/auth/confirm?token_hash=${hash}&type=recovery&next=${encodeURIComponent("/auth/recovery?from=email#done")}`),
    success.verify,
  );
  const location = response.headers.get("location");
  expect(location).toBe(`/auth/recovery?from=email#recovery_proof=${await recoveryProof("person-1", "session-1")}`);
  expect(location).not.toContain("://");
  expect(location).not.toContain("localhost");

  const blocked = verifier({ error: null });
  const errorResponse = await confirmAuthGet(
    new Request(`http://localhost:10000/auth/confirm?token_hash=${hash}&type=recovery&next=${encodeURIComponent("https://evil.example/phish")}`),
    blocked.verify,
  );
  const errorLocation = errorResponse.headers.get("location");
  expect(refusal(errorLocation)).toMatchObject({ code: "malformed_link", type: "recovery" });
  expect(errorLocation).not.toContain("://");
  expect(errorLocation).not.toContain("localhost");
  expect(blocked.calls).toHaveLength(0);
});

test("a refusal keeps only its own code: request error params and hostile codes never pass through", async () => {
  const { verify, report } = verifier({ error: { message: "expired" } });
  const response = await confirmAuthGet(
    confirmRequest(`token_hash=${hash}&type=recovery&error=access_denied&error_code=otp_expired`),
    verify,
    report,
  );
  expect(refusal(response.headers.get("location"))).toMatchObject({ code: "verify_failed", type: "recovery" });
  expect(new URL(response.headers.get("location") ?? "", origin).searchParams.get("error")).toBeNull();
  expect(response.headers.get("location")).not.toContain(hash);

  const hostile = verifier({ error: { code: "otp expired at the provider" } });
  const dropped = await confirmAuthGet(confirmRequest(`token_hash=${hash}&type=recovery`), hostile.verify, hostile.report);
  expect(refusal(dropped.headers.get("location"))).toMatchObject({ code: "verify_failed", type: "recovery" });
});

test("the confirm route wires verifyOtp through the server client", () => {
  const source = readFileSync(new URL("../app/auth/confirm/route.ts", import.meta.url), "utf8");
  expect(source).toContain("createClient()");
  expect(source).toContain("verifyOtp");
  expect(source).toContain("confirmAuthGet");
});

const linked: AuthMail[] = [
  { action: "recovery", recipient: "ada@example.test", tokenHash: hash, redirectTo: `${origin}/auth/recovery` },
  { action: "invite", recipient: "ada@example.test", tokenHash: hash, redirectTo: `${origin}/` },
  { action: "email_change", audience: "old_address", recipient: "ada@example.test", tokenHash: hash, redirectTo: `${origin}/`, newEmail: "new@example.test" },
  { action: "email_change", audience: "new_address", recipient: "new@example.test", tokenHash: hash, redirectTo: `${origin}/`, newEmail: "new@example.test" },
];

function assertPlainUrls(text: string) {
  for (const line of text.split("\n")) {
    if (!line.includes("https://") && !line.includes("{{ .SiteURL }}")) continue;
    expect(line).toMatch(/^(?:https:\/\/\S+|\{\{ \.SiteURL \}\}\/auth\/confirm\?token_hash=\{\{ \.TokenHash \}\}&type=\w+&next=\/\S*)$/);
    expect(line).not.toMatch(/[.,;:!?)>\]]$|%2E$/);
  }
}

test("recovery, invite and both email-change mails stay on the app confirm route with no trailing punctuation", async () => {
  for (const mail of linked) {
    const rendered = await renderAuthMail(mail, origin, 3600, sentAt);
    expect(`${rendered.subject}\n${rendered.html}\n${rendered.text}`).not.toContain("supabase.co");
    expect(rendered.html).not.toContain("/auth/v1/verify");
    assertPlainUrls(rendered.text);
    expect(rendered.text).toContain("/auth/confirm?token_hash=");
    expect(rendered.html).toContain("/auth/confirm?token_hash=");
  }
});

function assertCodeOnly(rendered: { subject: string; html: string; text: string }, code: string) {
  expect(rendered.subject.startsWith(`${code} `)).toBe(true);
  expect(rendered.text).toContain(code);
  expect(rendered.html).toContain('class="code"');
  expect(rendered.html).not.toContain('class="button"');
  expect(rendered.html).not.toMatch(/href="https?:/);
  expect(rendered.text).not.toMatch(/https?:\/\//);
  expect(`${rendered.html}\n${rendered.text}`).not.toContain("/auth/");
}

test("signup and magic link are code only and name the recipient", async () => {
  const signup = await renderAuthMail(
    { action: "signup", recipient: "ada@example.test", tokenHash: hash, redirectTo: `${origin}/`, token: "55070219" },
    origin,
    3600,
    sentAt,
  );
  expect(signup.subject).toBe("55070219 es tu código de Cuadrao");
  expect(signup.text).toContain("Escribe este código en Cuadrao para confirmar tu cuenta:");
  expect(signup.text).toContain("El código vence en 1 hora y solo se puede usar una vez.");
  expect(signup.text).toContain("Lo pediste para ada@example.test. Si no fuiste tú, ignora este correo.");
  expect(signup.html).toContain("Escríbelo en Cuadrao para confirmar tu cuenta. Vence en 1 hora.");
  assertCodeOnly(signup, "55070219");
  const magic = await renderAuthMail(
    { action: "magiclink", recipient: "ada@example.test", tokenHash: hash, redirectTo: `${origin}/`, token: "55070219" },
    origin,
    3600,
    sentAt,
  );
  expect(magic.subject).toBe("55070219 es tu código para entrar a Cuadrao");
  expect(magic.text).toContain("Escribe este código en Cuadrao para entrar:");
  expect(magic.text).toContain("Lo pediste para ada@example.test. Si no fuiste tú, ignora este correo. Nadie puede entrar sin este código.");
  expect(magic.html).toContain("Escríbelo en Cuadrao para entrar. Vence en 1 hora.");
  assertCodeOnly(magic, "55070219");
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
});

test("dashboard paste wires confirm links and code-only templates", async () => {
  const records = await buildDashboardAuthPaste();
  expect(records.map((record) => record.file)).toEqual(["confirmation", "magic_link", "recovery", "invite", "email_change"]);
  const byFile = Object.fromEntries(records.map((record) => [record.file, record]));
  expect(byFile.confirmation.subjectField).toBe("mailer_subjects_confirmation");
  expect(byFile.confirmation.bodyField).toBe("mailer_templates_confirmation_content");
  expect(byFile.confirmation.subject).toBe("{{ .Token }} es tu código de Cuadrao");
  expect(byFile.confirmation.text).toContain("Lo pediste para {{ .Email }}.");
  assertCodeOnly(byFile.confirmation, "{{ .Token }}");
  expect(byFile.magic_link.subjectField).toBe("mailer_subjects_magic_link");
  expect(byFile.magic_link.bodyField).toBe("mailer_templates_magic_link_content");
  expect(byFile.magic_link.subject).toBe("{{ .Token }} es tu código para entrar a Cuadrao");
  expect(byFile.magic_link.text).toContain("Nadie puede entrar sin este código.");
  assertCodeOnly(byFile.magic_link, "{{ .Token }}");
  expect(byFile.recovery.subjectField).toBe("mailer_subjects_recovery");
  expect(byFile.recovery.bodyField).toBe("mailer_templates_recovery_content");
  expect(byFile.recovery.subject).toBe("Cambio de contraseña en Cuadrao");
  expect(byFile.recovery.text.split("\n")).toContain("{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=recovery&next=/auth/recovery");
  expect(byFile.invite.subjectField).toBe("mailer_subjects_invite");
  expect(byFile.invite.bodyField).toBe("mailer_templates_invite_content");
  expect(byFile.invite.subject).toBe("Te invitaron a Cuadrao");
  expect(byFile.invite.text.split("\n")).toContain("{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=invite&next=/");
  expect(byFile.email_change.subjectField).toBe("mailer_subjects_email_change");
  expect(byFile.email_change.bodyField).toBe("mailer_templates_email_change_content");
  expect(byFile.email_change.subject).toBe("Confirma tu nuevo correo");
  expect(byFile.email_change.text.split("\n")).toContain("{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=email_change&next=/");
  for (const record of records) {
    expect(`${record.subject}\n${record.html}\n${record.text}`).not.toContain("supabase.co");
    expect(record.text).not.toContain(hash);
    expect(record.html).not.toContain(hash);
    expect(record.text).toContain("Cuadrao LLC");
    expect(record.text).not.toContain("Cuadrao LLC,");
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
  const coded = renderAccountEmail({
    title: "Tu código de Cuadrao",
    paragraphs: [],
    code: "{{ .Token }}",
  });
  expect(coded.text).toContain("{{ .Token }}");
  expect(() => renderAccountEmail({
    title: "Cambio de contraseña en Cuadrao",
    paragraphs: [],
    code: "not-a-code",
  })).toThrow();
});

test("a recovery page reload needs proof from a recovery exchange", async () => {
  const port: AuthSecurityPort = {
    async exchangeCodeForSession() {
      return { data: { redirectType: "recovery" }, error: null };
    },
    async updateUser() {
      return { error: null };
    },
    async signOut() {
      return { error: null };
    },
    async getValidatedSession() {
      return { userId: "person-1", sessionId: "session-1" };
    },
  };
  const values = new Map<string, string>();
  const store = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
  const ordinarySession = createAuthSecurityActions(port, async () => undefined, store);
  expect(await ordinarySession.hasRecoverySession()).toBe(false);
  await ordinarySession.exchangeRecoveryCode("recovery-code");
  const reloaded = createAuthSecurityActions(port, async () => undefined, store);
  expect(await reloaded.hasRecoverySession()).toBe(true);
  const failed = createAuthSecurityActions({ ...port, getValidatedSession: async () => {
    throw new Error("synthetic session read failure");
  } }, async () => undefined, store);
  expect(await failed.hasRecoverySession()).toBe(false);
  const page = readFileSync(new URL("../app/auth/recovery/page.tsx", import.meta.url), "utf8");
  const reset = readFileSync(new URL("../components/auth/RecoveryReset.tsx", import.meta.url), "utf8");
  expect(page).toContain("<RecoveryReset />");
  const codeRead = reset.indexOf('.get("code")');
  const queryRemoved = reset.indexOf('window.history.replaceState(null, "", window.location.pathname)');
  const session = reset.indexOf("hasRecoverySession()");
  const exchange = reset.indexOf(".exchangeRecoveryCode(code)");
  expect(codeRead).toBeGreaterThan(-1);
  expect(queryRemoved).toBeGreaterThan(-1);
  expect(session).toBeGreaterThan(-1);
  expect(exchange).toBeGreaterThan(-1);
  expect(session).toBeGreaterThan(queryRemoved);
  expect(exchange).toBeGreaterThan(queryRemoved);
  expect(queryRemoved).toBeGreaterThan(codeRead);
});
