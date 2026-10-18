import { expect, test } from "bun:test";
import { signupWithEmail } from "../lib/argus-api";
import { registerGuestAccount } from "../lib/guest-api";
import { bootstrapGuest } from "../lib/guest-session";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

const confirmedAt = "2026-10-17T12:00:00.000Z";

const approved = {
  en: {
    checkbox: "I confirm I'm 18 or older.",
    missing: "To continue, confirm you're 18 or older.",
    rejected: "We couldn't save your age confirmation. Check the box and try again.",
    disclosure:
      "When you create your account, we save with it when you confirmed you're 18 or older. We don't store your date of birth.",
  },
  es: {
    checkbox: "Confirmo que tengo 18 años o más.",
    missing: "Para continuar, confirma que tienes 18 años o más.",
    rejected: "No pudimos guardar tu confirmación de edad. Marca la casilla e inténtalo de nuevo.",
    disclosure:
      "Al crear tu cuenta, guardamos con ella cuándo confirmaste que tienes 18 años o más. No guardamos tu fecha de nacimiento.",
  },
} as const;

const removed = {
  en: "We store when you confirmed you are 18 or older in this browser until you clear its local data.",
  es: "Guardamos en este navegador cuándo confirmaste que tienes 18 años o más, hasta que borres sus datos locales.",
} as const;

test("signup sends the supplied instant and guest bootstrap does not", async () => {
  const originalFetch = globalThis.fetch;
  const calls: { path: string; body: Record<string, unknown> }[] = [];
  globalThis.fetch = (async (input, init) => {
    calls.push({ path: String(input), body: JSON.parse(String(init?.body)) });
    return Response.json({ user: { id: "member" }, session: null, authenticated: true, account_kind: "guest" });
  }) as typeof fetch;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  try {
    await expect(signupWithEmail({ email: "adult@example.com", password: "password123", language: "en", age_confirmed_at: "" })).rejects.toMatchObject({ code: "age_confirmation_required" });
    await expect(registerGuestAccount({ email: "adult@example.com", password: "password123", language: "en", source_conversation_id: "chat", age_confirmed_at: "" })).rejects.toMatchObject({ code: "age_confirmation_required" });
    expect(calls).toHaveLength(0);
    await bootstrapGuest({ captcha_token: "proof", language: "en" });
    await registerGuestAccount({ email: "adult@example.com", password: "password123", language: "en", source_conversation_id: "chat", age_confirmed_at: confirmedAt });
    await signupWithEmail({ email: "adult@example.com", password: "password123", language: "en", age_confirmed_at: confirmedAt });
    const guest = calls.find(({ path }) => path.endsWith("/auth/guest"));
    const account = calls.filter(({ path }) => path.endsWith("/auth/signup") || path.endsWith("/auth/guest/signup"));
    expect(guest?.body).not.toHaveProperty("age_confirmed_at");
    expect(account).toHaveLength(2);
    expect(account.every(({ body }) => body.age_confirmed_at === confirmedAt)).toBe(true);
  } finally { globalThis.fetch = originalFetch; }
});

test("age confirmation copy matches the approved English and Spanish text", () => {
  expect(en.auth.age_confirmation).toEqual({
    checkbox: approved.en.checkbox,
    missing: approved.en.missing,
    rejected: approved.en.rejected,
  });
  expect(es.auth.age_confirmation).toEqual({
    checkbox: approved.es.checkbox,
    missing: approved.es.missing,
    rejected: approved.es.rejected,
  });
  expect(en.legal.privacy.sections.cookies.items.preferences.body).toContain(approved.en.disclosure);
  expect(es.legal.privacy.sections.cookies.items.preferences.body).toContain(approved.es.disclosure);
  expect(en.legal.privacy.sections.cookies.items.preferences.body).not.toContain(removed.en);
  expect(es.legal.privacy.sections.cookies.items.preferences.body).not.toContain(removed.es);
  expect(JSON.stringify(en)).not.toContain("cuadrao-age-confirmed-at");
  expect(JSON.stringify(es)).not.toContain("cuadrao-age-confirmed-at");
  expect(en.auth.age_confirmation.checkbox).not.toBe(es.auth.age_confirmation.checkbox);
});

test("a missing age field and any other age failure use the approved messages", async () => {
  const { localizedAuthErrorMessage } = await import("../components/auth/AuthForm");
  const translate = (catalog: typeof en) => (key: string, fallback: string) => {
    const value = key.split(".").reduce<unknown>((current, segment) => {
      if (typeof current !== "object" || current === null) return undefined;
      return (current as Record<string, unknown>)[segment];
    }, catalog);
    return typeof value === "string" ? value : fallback;
  };
  const coded = (code: string) => Object.assign(new Error("Confirmo que tengo 18 años o más."), { code });
  expect(localizedAuthErrorMessage(coded("age_confirmation_required"), translate(en))).toBe(approved.en.missing);
  expect(localizedAuthErrorMessage(coded("age_confirmation_required"), translate(es))).toBe(approved.es.missing);
  expect(localizedAuthErrorMessage(coded("age_confirmation_invalid"), translate(en))).toBe(approved.en.rejected);
  expect(localizedAuthErrorMessage(coded("age_confirmation_invalid"), translate(es))).toBe(approved.es.rejected);
  expect(localizedAuthErrorMessage(coded("age_confirmation_unsavable"), translate(en))).toBe(approved.en.rejected);
  expect(localizedAuthErrorMessage(coded("age_confirmation_unsavable"), translate(es))).toBe(approved.es.rejected);
});
