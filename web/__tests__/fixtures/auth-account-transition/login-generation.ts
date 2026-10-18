import { confirmAge } from "@/lib/age-confirmation";
import { afterEach, expect, mock, test } from "bun:test";
import { invalidateBrowserAuth } from "@/lib/browser-auth-generation";
let persistCalls = 0;
mock.module("@/lib/supabase-client", () => ({ getSupabaseClient: () => ({ auth: { setSession: async () => { persistCalls++; return { data: { session: { user: { id: "new" } } }, error: null }; } } }) }));
mock.module("@/lib/guest-captcha", () => ({ acquirePasswordAuthCaptchaToken: async () => null }));
const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });
test("logout invalidates delayed login and signup responses before they can restore a session", async () => {
  confirmAge();
  const { loginWithEmail, signupWithEmail } = await import("@/lib/argus-api");
  for (const login of [() => loginWithEmail({ email: "fixture@example.test", password: "fixture" }), () => signupWithEmail({ email: "fixture@example.test", password: "fixture", language: "en" })]) {
    let release!: (response: Response) => void;
    globalThis.fetch = mock(() => new Promise<Response>(resolve => { release = resolve; })) as typeof fetch;
    const pending = login();
    await new Promise(resolve => setTimeout(resolve, 0));
    invalidateBrowserAuth();
    release(Response.json({ session: { access_token: "new", refresh_token: "new-refresh" } }));
    await expect(pending).rejects.toThrow("Browser session changed");
  }
  expect(persistCalls).toBe(0);
});
