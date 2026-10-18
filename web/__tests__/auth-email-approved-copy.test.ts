import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { parseAuthMail, renderAuthMail, type AuthMail } from "../server/emails/auth-actions";
import { emailExpiry } from "../server/emails/expiry";
import { DISABLED_SECURITY_NOTICES } from "../server/emails/security-notices";

const base = { recipient: "old@example.test", tokenHash: "a".repeat(64), redirectTo: "https://app.example.test/" };
const signin: AuthMail[] = [
  { ...base, action: "signup", token: "123456" },
  { ...base, action: "magiclink", token: "123456" },
  { ...base, action: "recovery" },
  { ...base, action: "email_change", audience: "old_address", newEmail: "new@example.test" },
  { ...base, action: "email_change", audience: "new_address", recipient: "new@example.test", newEmail: "new@example.test" },
  { action: "reauthentication", recipient: base.recipient, token: "123456" },
];
const security: AuthMail[] = [
  { action: "password_changed_notification", recipient: base.recipient },
  { action: "email_changed_notification", recipient: base.recipient, newEmail: "new@example.test" },
];
const sentAt = new Date("2026-10-17T02:05:00Z");

for (const [index, mail] of [...signin, ...security].entries()) {
  test(`approved HTML and plain text ${mail.action} ${index}`, async () => {
    const rendered = await renderAuthMail(mail, "https://auth.example.test", 3600, sentAt);
    expect(rendered).toMatchSnapshot();
    expect(rendered.html).toContain('<div class="preheader" style="display:none;');
    expect(rendered.text).toContain("Hola,");
    expect(rendered.text).toContain("Saludos,\nCuadrao");
    expect(rendered.html).not.toMatch(/Argus|get-argus|onrender\.com/);
    if ("token" in mail) {
      expect(rendered.subject).toStartWith("123456 ");
      expect(rendered.html.indexOf("Hola,")).toBeLessThan(rendered.html.indexOf('class="code"'));
      expect(rendered.text.indexOf("Hola,")).toBeLessThan(rendered.text.indexOf("123456"));
    }
  });
}

test("local 60-second configuration produces truthful expiry in all sign-in mail", async () => {
  for (const mail of signin) {
    const rendered = await renderAuthMail(mail, "https://auth.example.test", 60, sentAt);
    expect(rendered.html).toContain("1 minuto");
    expect(rendered.text).toContain("1 minuto");
    expect(rendered.text).not.toContain("1 hora");
  }
  expect(emailExpiry(1)).toBe("1 segundo");
  expect(emailExpiry(90)).toBe("90 segundos");
  expect(emailExpiry(120)).toBe("2 minutos");
  expect(emailExpiry(7200)).toBe("2 horas");
  for (const value of [0, -1, NaN, Infinity, 1.5]) expect(() => emailExpiry(value)).toThrow();
});

test("security notices show send time in RD and old-address notice has no reset or action link", async () => {
  const password = await renderAuthMail(security[0], "https://auth.example.test", 3600, sentAt);
  expect(password.text).toContain("16 de octubre de 2026");
  expect(password.text).toMatch(/10:05.*p\.?\s*m\.?/);
  expect(password.text).toContain('"¿Olvidaste tu contraseña?"');
  const changed = await renderAuthMail(security[1], "https://auth.example.test", 3600, sentAt);
  expect(changed.text).toContain("de old@example.test a n***@example.test");
  expect(changed.text).toContain("respondiendo a este correo para recuperar tu cuenta.");
  for (const part of [changed.html, changed.text]) {
    expect(part).not.toContain("new@example.test");
    expect(part).not.toContain("contraseña?");
    expect(part).not.toContain("/auth/");
  }
  expect(changed.html).not.toContain('class="button"');
});

test("committed notification flags enable exactly the two approved notices", () => {
  const config = Bun.TOML.parse(readFileSync(new URL("../../supabase/config.toml", import.meta.url), "utf8")) as { auth: { email: { notification: Record<string, {enabled: boolean}> } } };
  const flags = config.auth.email.notification;
  expect(Object.entries(flags).filter(([, value]) => value.enabled).map(([key]) => key).sort()).toEqual(["email_changed", "password_changed"]);
  for (const action of DISABLED_SECURITY_NOTICES) expect(flags[action.replace("_notification", "")].enabled).toBe(false);
});

test("notification recipients derive from signed documented fields and disabled actions need no tokens", () => {
  const payload = { user: {email: "new@example.test"}, email_data: {email_action_type: "email_changed_notification", old_email: "old@example.test", site_url: "https://app.example.test", redirect_to: ""} };
  expect(parseAuthMail(payload, "https://app.example.test")).toEqual([{action: "email_changed_notification", recipient: "old@example.test", newEmail: "new@example.test"}]);
  for (const action of DISABLED_SECURITY_NOTICES) {
    expect(parseAuthMail({...payload, email_data: {...payload.email_data, email_action_type: action}}, "https://app.example.test")).toEqual([]);
  }
  for (const old_email of ["", "victim@example.test\r\nBcc: another@example.test"]) {
    expect(() => parseAuthMail({...payload, email_data: {...payload.email_data, old_email}}, "https://app.example.test")).toThrow();
  }
});
