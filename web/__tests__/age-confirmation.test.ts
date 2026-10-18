import { expect, test } from "bun:test";
import { confirmAge, readAgeConfirmation, requireAgeConfirmation } from "../lib/age-confirmation";
import { signupWithEmail } from "../lib/argus-api";
import { registerGuestAccount } from "../lib/guest-api";
import { bootstrapGuest } from "../lib/guest-session";

test("entry refuses absent confirmation before network, then conversion keeps the same instant", async () => {
  const originalFetch = globalThis.fetch;
  const calls: { path: string; body: Record<string, unknown> }[] = [];
  globalThis.fetch = (async (input, init) => {
    calls.push({ path: String(input), body: JSON.parse(String(init?.body)) });
    return Response.json({ user: { id: "member" }, session: null });
  }) as typeof fetch;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  try {
    expect(readAgeConfirmation()).toBeNull();
    expect(requireAgeConfirmation).toThrow("age_confirmation_required");
    await expect(signupWithEmail({ email: "adult@example.com", password: "password123", language: "en" })).rejects.toMatchObject({ code: "age_confirmation_required" });
    await expect(registerGuestAccount({ email: "adult@example.com", password: "password123", language: "en", source_conversation_id: "chat" })).rejects.toMatchObject({ code: "age_confirmation_required" });
    await expect(bootstrapGuest({ captcha_token: "proof", language: "en" })).rejects.toMatchObject({ code: "age_confirmation_required" });
    expect(calls).toHaveLength(0);
    const first = confirmAge();
    expect(confirmAge()).toBe(first);
    await bootstrapGuest({ captcha_token: "proof", language: "en" });
    await registerGuestAccount({ email: "adult@example.com", password: "password123", language: "en", source_conversation_id: "chat" });
    await signupWithEmail({ email: "adult@example.com", password: "password123", language: "en" });
    const entries = calls.filter(({ path }) => !path.endsWith("/handoffs"));
    expect(entries).toHaveLength(3);
    expect(entries.every(({ body }) => body.age_confirmed_at === first)).toBe(true);
  } finally { globalThis.fetch = originalFetch; }
});
