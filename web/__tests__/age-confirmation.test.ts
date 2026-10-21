import { expect, test } from "bun:test";
import { signupWithEmail } from "../lib/argus-api";
import { registerGuestAccount } from "../lib/guest-api";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

test("web signup and guest signup post without an age confirmation", async () => {
  const originalFetch = globalThis.fetch;
  const calls: { path: string; body: Record<string, unknown> }[] = [];
  globalThis.fetch = (async (input, init) => {
    calls.push({ path: String(input), body: JSON.parse(String(init?.body)) });
    return Response.json({ user: { id: "member" }, session: null, authenticated: true, account_kind: "guest" });
  }) as typeof fetch;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  try {
    const signup = await signupWithEmail({ email: "adult@example.com", password: "password123", language: "en" });
    await registerGuestAccount({ email: "adult@example.com", password: "password123", language: "en", source_conversation_id: "chat" });
    const account = calls.filter(({ path }) => path.endsWith("/auth/signup") || path.endsWith("/auth/guest/signup"));
    expect(signup.needsEmailConfirmation).toBe(true);
    expect(account).toHaveLength(2);
    for (const { body } of account) expect(body).not.toHaveProperty("age_confirmed_at");
  } finally { globalThis.fetch = originalFetch; }
});

test("the age checkbox strings are gone", () => {
  expect(en.auth).not.toHaveProperty("age_confirmation");
  expect(es.auth).not.toHaveProperty("age_confirmation");
});

test("an age error code from the server reads as the generic auth error", async () => {
  const { localizedAuthErrorMessage } = await import("../components/auth/AuthForm");
  const translate = (_key: string, fallback: string) => fallback;
  const coded = (code: string) => Object.assign(new Error(code), { code });
  const generic = localizedAuthErrorMessage(coded("not_a_known_code"), translate);
  expect(localizedAuthErrorMessage(coded("age_confirmation_required"), translate)).toBe(generic);
  expect(localizedAuthErrorMessage(coded("age_confirmation_invalid"), translate)).toBe(generic);
});
