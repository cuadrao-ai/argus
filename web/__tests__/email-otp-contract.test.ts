import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { EMAIL_OTP_LENGTH, EMAIL_OTP_PATTERN, isEmailOtp } from "../lib/email-otp-contract";
import { normalizeEmailOtp, verifyEmailOtp } from "../lib/email-otp";
import { parseAuthMail, renderAuthMail } from "../server/emails/auth-actions";
import { renderAccountEmail } from "../server/emails/account-layout.generated";
import { renderAccountEmail as renderMarketingEmail } from "../../marketing/lib/email/account-layout";

const invalid = ["", "123456", "1234567", "123456789", "1234567890", "0123 4567", " 01234567", "01234567 ", "01234567\n", "０１２３４５６７", "0123456a"];
const payload = (token: string, action = "signup") => ({
  user: { email: "person@example.test" },
  email_data: { email_action_type: action, site_url: "https://app.example.test", redirect_to: "", token_hash: "a".repeat(64), token },
});

test("the form and local email config use the shared eight-digit contract", () => {
  expect(EMAIL_OTP_LENGTH).toBe(8);
  expect(EMAIL_OTP_PATTERN.source).toBe(`^[0-9]{${EMAIL_OTP_LENGTH}}$`);
  const config = Bun.TOML.parse(readFileSync(new URL("../../supabase/config.toml", import.meta.url), "utf8")) as { auth: { email: { otp_length: number } } };
  expect(config.auth.email.otp_length).toBe(EMAIL_OTP_LENGTH);
  const form = readFileSync(new URL("../components/auth/AuthForm.tsx", import.meta.url), "utf8");
  expect(form).toContain('import { EMAIL_OTP_LENGTH } from "@/lib/email-otp-contract"');
  expect(form).not.toContain("value.replace(/\\s+/g");
});

test("every code boundary preserves exact digits and leading zeros", async () => {
  const token = "01234567";
  expect(isEmailOtp(token)).toBe(true);
  expect(normalizeEmailOtp(token)).toBe(token);
  const calls: unknown[] = [];
  await verifyEmailOtp({ email: "person@example.test", token, type: "signup" }, async input => { calls.push(input); return { error: null }; });
  expect(calls).toEqual([{ email: "person@example.test", token, type: "signup" }]);
  for (const action of ["signup", "magiclink", "reauthentication"]) {
    const [mail] = parseAuthMail(payload(token, action), "https://app.example.test");
    expect(await renderAuthMail(mail, "https://app.example.test", 3600)).toMatchObject({ subject: expect.stringContaining(token) });
  }
  for (const render of [renderAccountEmail, renderMarketingEmail]) {
    expect(render({ title: "Code", paragraphs: [], code: token }).text).toContain(token);
    expect(render({ title: "Code", paragraphs: [], code: "{{ .Token }}" }).text).toContain("{{ .Token }}");
  }
});

test.each(invalid)("every runtime boundary rejects unchanged invalid code %j", async token => {
  expect(isEmailOtp(token)).toBe(false);
  expect(normalizeEmailOtp(token)).toBeNull();
  let called = false;
  await expect(verifyEmailOtp({ email: "person@example.test", token, type: "signup" }, async () => { called = true; return { error: null }; })).rejects.toMatchObject({ code: "otp_rejected" });
  expect(called).toBe(false);
  for (const action of ["signup", "magiclink", "reauthentication"]) {
    expect(() => parseAuthMail(payload(token, action), "https://app.example.test")).toThrow();
    await expect(renderAuthMail({ action: "signup", recipient: "person@example.test", tokenHash: "a".repeat(64), redirectTo: "", token }, "https://app.example.test", 3600)).rejects.toThrow();
  }
  for (const field of ["token", "token_new"]) {
    const value = payload("01234567", "email_change");
    expect(() => parseAuthMail({
      user: { ...value.user, new_email: "new@example.test" },
      email_data: { ...value.email_data, token_hash_new: "b".repeat(64), token_new: "76543210", [field]: token },
    }, "https://app.example.test")).toThrow();
  }
  for (const render of [renderAccountEmail, renderMarketingEmail]) {
    expect(() => render({ title: "Code", paragraphs: [], code: token })).toThrow();
  }
});

test("runtime payloads and rendering reject the trusted template placeholder", async () => {
  expect(() => parseAuthMail(payload("{{ .Token }}"), "https://app.example.test")).toThrow();
  await expect(renderAuthMail({ action: "signup", recipient: "person@example.test", tokenHash: "a".repeat(64), redirectTo: "", token: "{{ .Token }}" }, "https://app.example.test", 3600)).rejects.toThrow();
});
