import { installEmailFixture } from "./helpers/email-fixture";
installEmailFixture();
import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { parseAuthMail, renderAuthMail, type AuthMail } from "../server/emails/auth-actions";
import { renderAccountEmail } from "../server/emails/account-layout.generated";
import { assertEmailPresentation } from "./helpers/email-presentation";
import { emailExpiry } from "../server/emails/expiry";
import spanish from "../public/locales/es-419/common.json";
import english from "../public/locales/en/common.json";
import { DISABLED_SECURITY_NOTICES, renderSecurityMail } from "../server/emails/security-notices";

const base = { recipient: "old@example.test", tokenHash: "a".repeat(64), redirectTo: "https://app.example.test/" };
const signin: AuthMail[] = [
  { ...base, action: "signup", token: "01234567" },
  { ...base, action: "magiclink", token: "01234567" },
  { ...base, action: "recovery" },
  { ...base, action: "invite" },
  { ...base, action: "email_change", audience: "old_address", newEmail: "new@example.test" },
  { ...base, action: "email_change", audience: "new_address", recipient: "new@example.test", newEmail: "new@example.test" },
  { action: "reauthentication", recipient: base.recipient, token: "01234567" },
];
const security: AuthMail[] = [
  { action: "password_changed_notification", recipient: base.recipient },
  { action: "email_changed_notification", recipient: base.recipient, newEmail: "new@example.test" },
];
const sentAt = new Date("2026-10-17T02:05:00Z");

for (const [index, mail] of [...signin, ...security].entries()) {
  test(`approved HTML and plain text ${mail.action} ${index}`, async () => {
    const rendered = await renderAuthMail(mail, "https://app.example.test", 3600, sentAt);
    expect(rendered).toMatchSnapshot();
    assertEmailPresentation(rendered.html, rendered.text);
    expect(rendered.html).toContain('<div class="preheader" style="display:none;');
    expect(rendered.html).not.toContain(">Hola,</p>");
    expect(rendered.text).not.toContain("Hola,");
    expect(rendered.html).not.toContain("Saludos,<br>Cuadrao");
    expect(rendered.text).not.toContain("Saludos,\nCuadrao");
    expect(rendered.html).not.toMatch(/Argus|get-argus|onrender\.com/);
    if ("token" in mail) {
      expect(rendered.subject).toStartWith("01234567 ");
    }
  });
}

test("account templates render Cuadrao LLC and no postal address when the env is unset", async () => {
  delete process.env.MARKETING_POSTAL_ADDRESS;
  for (const mail of [...signin, ...security]) {
    const rendered = await renderAuthMail(mail, "https://auth.example.test", 3600, sentAt);
    expect(rendered.html).toContain(">Cuadrao LLC</p>");
    expect(rendered.text).toContain("\n\nCuadrao LLC");
    expect(rendered.html).not.toContain("Cuadrao LLC,");
    expect(rendered.text).not.toContain("Cuadrao LLC,");
    expect(rendered.html).not.toContain("Salir de la lista");
  }
});

test("auth and security mail render with the postal address unset and unsubscribe mail refuses", async () => {
  delete process.env.MARKETING_POSTAL_ADDRESS;
  const required = new Set([
    "signup",
    "magiclink",
    "recovery",
    "invite",
    "email_change",
    "reauthentication",
    "password_changed_notification",
    "email_changed_notification",
  ]);
  const seen = new Set<string>();
  for (const mail of [...signin, ...security]) {
    seen.add(mail.action);
    const rendered = await renderAuthMail(mail, "https://auth.example.test", 3600, sentAt);
    expect(rendered.html).toContain(">Cuadrao LLC</p>");
    expect(rendered.text).toContain("\n\nCuadrao LLC");
    expect(rendered.html).not.toContain("Cuadrao LLC,");
    expect(rendered.text).not.toContain("Cuadrao LLC,");
    expect(rendered.html).not.toContain("Salir de la lista");
  }
  expect(seen).toEqual(required);
  expect(signin.filter(mail => mail.action === "email_change").map(mail => mail.audience)).toEqual(["old_address", "new_address"]);
  expect(() => renderAccountEmail({
    title: "Lista",
    paragraphs: [],
    unsubscribeUrl: "https://example.test/leave",
  })).toThrow("postal address");
});

test("local 60-second configuration produces truthful expiry in all sign-in mail", async () => {
  for (const mail of signin) {
    const rendered = await renderAuthMail(mail, "https://app.example.test", 60, sentAt);
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

test("security notices omit send time and show the full new address without action links", async () => {
  const password = await renderAuthMail(security[0], "https://app.example.test", 3600, sentAt);
  expect(password.text).toContain("La contraseña de tu cuenta de Cuadrao se cambió.");
  expect(password.text).toContain('"¿Olvidaste tu contraseña?"');
  const changed = await renderAuthMail(security[1], "https://app.example.test", 3600, sentAt);
  expect(changed.text).toContain("de old@example.test a new@example.test.");
  expect(changed.text).toContain("Si no fuiste tú, escríbenos de inmediato a hola@cuadrao.ai para recuperar tu cuenta.");
  for (const part of [changed.html, changed.text]) {
    expect(part).not.toContain("contraseña?");
    expect(part).not.toContain("/auth/");
    expect(part).not.toContain("***");
  }
  for (const rendered of [password, changed]) {
    expect(rendered.text).not.toMatch(/2026|10:05|hora de RD/);
    expect(rendered.html).not.toContain('class="button"');
  }
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


test("Auth security catalogs have matching keys and placeholders", () => {
  const spanishCopy = spanish.account_email.auth_security;
  const englishCopy = english.account_email.auth_security;
  const keys = ["email_changed_description", "password_changed_description", "recovery_contact", "safety_warning"] as const;
  expect(Object.keys(spanishCopy)).toEqual([...keys]);
  expect(Object.keys(englishCopy)).toEqual([...keys]);
  for (const key of keys) {
    expect(englishCopy[key].trim()).not.toBe("");
    const placeholders = (value: string) => [...value.matchAll(/\{\{(\w+)\}\}/g)].map(match => match[1]).sort();
    expect(placeholders(englishCopy[key])).toEqual(placeholders(spanishCopy[key]));
  }
  expect(spanishCopy.email_changed_description).toContain("{{oldEmail}}");
  expect(spanishCopy.email_changed_description).toContain("{{newEmail}}");
});

test("security rendering reads Spanish catalog values and preserves literal address replacements", () => {
  const copy = spanish.account_email.auth_security;
  const original = { ...copy };
  try {
    for (const key of Object.keys(copy) as Array<keyof typeof copy>) copy[key] = `Synthetic ${key} <&>`;
    const password = renderSecurityMail({ action: "password_changed_notification", recipient: base.recipient }, sentAt);
    const changed = renderSecurityMail({ action: "email_changed_notification", recipient: base.recipient, newEmail: "new@example.test" }, sentAt);
    for (const [rendered, keys] of [
      [password, ["password_changed_description", "safety_warning"]],
      [changed, ["email_changed_description", "recovery_contact", "safety_warning"]],
    ] as const) {
      for (const key of keys) {
        expect(rendered.text).toContain(`Synthetic ${key} <&>`);
        expect(rendered.html).toContain(`Synthetic ${key} &lt;&amp;&gt;`);
      }
    }
    copy.email_changed_description = original.email_changed_description;
    for (const [recipient, newEmail] of [["old$&{{newEmail}}@example.test", "new$'@example.test"], ["{{ .OldEmail }}", "{{ .Email }}"]]) {
      const rendered = renderSecurityMail({ action: "email_changed_notification", recipient, newEmail }, sentAt);
      expect(rendered.text).toContain(`de ${recipient} a ${newEmail}.`);
      expect(rendered.html).toContain(recipient.replaceAll("&", "&amp;"));
      expect(rendered.html).toContain(newEmail.replace("'", "&#39;"));
    }
  } finally {
    Object.assign(copy, original);
  }
});
