import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { loginWithEmail, signupWithEmail } from "../lib/argus-api";
import { registerGuestAccount } from "../lib/guest-api";
import { requestPasswordRecovery } from "../lib/auth-security";

const root = join(import.meta.dir, "..");
const originalFetch = globalThis.fetch;
const originalNodeEnv = process.env.NODE_ENV;
const originalLocalToken =
  process.env.NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN;
const originalCuadraoSiteKey = process.env.NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY;
const originalTurnstileSiteKey =
  process.env.NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;

function successfulJson(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  process.env.NODE_ENV = "test";
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  delete process.env.NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN;
  delete process.env.NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY;
  delete process.env.NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  process.env.NODE_ENV = originalNodeEnv;
  if (originalLocalToken === undefined) {
    delete process.env.NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN;
  } else {
    process.env.NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN = originalLocalToken;
  }
  if (originalCuadraoSiteKey === undefined) {
    delete process.env.NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY;
  } else {
    process.env.NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY = originalCuadraoSiteKey;
  }
  if (originalTurnstileSiteKey === undefined) {
    delete process.env.NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY;
  } else {
    process.env.NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY =
      originalTurnstileSiteKey;
  }
  if (originalMockAuth === undefined) {
    delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  } else {
    process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  }
});

describe("password auth CAPTCHA and confirmation contract", () => {
  test("signup acquires a CAPTCHA token and reports a sessionless confirmation", async () => {
    let body: Record<string, unknown> | null = null;
    globalThis.fetch = (async (_input, init) => {
      body = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return successfulJson({ user: { id: "user-1" }, session: null });
    }) as typeof globalThis.fetch;

    const result = await signupWithEmail({
      email: "alpha@example.com",
      password: "password123",
      language: "en",
      age_confirmed_at: "2026-10-17T12:00:00.000Z",
    });

    expect(body).toMatchObject({
      email: "alpha@example.com",
      captcha_token: "argus-local-browser-qa",
      age_confirmed_at: "2026-10-17T12:00:00.000Z",
    });
    expect(result.response.session).toBeNull();
    expect(result.needsEmailConfirmation).toBe(true);
  });

  test("signup with a returned session preserves the authenticated outcome", async () => {
    globalThis.fetch = (async () =>
      successfulJson({ user: { id: "user-1" }, session: {} })) as typeof fetch;

    const result = await signupWithEmail({
      email: "alpha@example.com",
      password: "password123",
      language: "en",
      age_confirmed_at: "2026-10-17T12:00:00.000Z",
    });

    expect(result.needsEmailConfirmation).toBe(false);
  });

  test("guest signup prepares the durable handoff before calling provider signup", async () => {
    const requests: Array<{ path: string; body: Record<string, unknown> }> = [];
    globalThis.fetch = (async (input, init) => {
      const path = new URL(String(input)).pathname;
      requests.push({
        path,
        body: JSON.parse(String(init?.body)) as Record<string, unknown>,
      });
      if (path.endsWith("/auth/guest/handoffs")) {
        return new Response(
          JSON.stringify({
            handoff_id: "handoff-1",
            expires_at: "2026-08-19T12:00:00Z",
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        );
      }
      return successfulJson({ user: { id: "user-1" }, session: null });
    }) as typeof globalThis.fetch;

    const result = await registerGuestAccount({
      email: "alpha@example.com",
      password: "password123",
      language: "es-419",
      display_name: "Alex",
      age_confirmed_at: "2026-10-17T12:00:00.000Z",
      source_conversation_id: "conversation-1",
      pending_action: {
        reason: "keep_history",
        conversation_id: "conversation-1",
        action_id: "keep-1",
      },
    });

    expect(requests.map((request) => request.path)).toEqual([
      "/api/v1/auth/guest/handoffs",
      "/api/v1/auth/guest/signup",
    ]);
    expect(requests[0]?.body).toEqual({
      handoff_kind: "new_account_signup",
      destination_email: "alpha@example.com",
      source_conversation_id: "conversation-1",
      pending_action: {
        reason: "keep_history",
        conversation_id: "conversation-1",
        action_id: "keep-1",
      },
    });
    expect(requests[1]?.body).toMatchObject({
      email: "alpha@example.com",
      password: "password123",
      language: "es-419",
      display_name: "Alex",
      captcha_token: "argus-local-browser-qa",
      age_confirmed_at: "2026-10-17T12:00:00.000Z",
    });
    expect(result.needsEmailConfirmation).toBe(true);
  });

  test("password login acquires a CAPTCHA token at the shared API boundary", async () => {
    let body: Record<string, unknown> | null = null;
    globalThis.fetch = (async (_input, init) => {
      body = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return successfulJson({ user: { id: "user-1" }, session: {} });
    }) as typeof globalThis.fetch;

    await loginWithEmail({
      email: "alpha@example.com",
      password: "password123",
    });

    expect(body).toMatchObject({
      email: "alpha@example.com",
      captcha_token: "argus-local-browser-qa",
    });
  });

  test("password recovery acquires a CAPTCHA token at the shared browser boundary", async () => {
    let body: Record<string, unknown> | null = null;
    globalThis.fetch = (async (_input, init) => {
      body = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return new Response(JSON.stringify({ accepted: true }), { status: 202 });
    }) as typeof globalThis.fetch;

    await requestPasswordRecovery("alpha@example.com");

    expect(body).toEqual({
      email: "alpha@example.com",
      captcha_token: "argus-local-browser-qa",
    });
  });

  test("CAPTCHA acquisition failure is safe and classified before fetch", async () => {
    process.env.NODE_ENV = "production";
    let fetchCalls = 0;
    globalThis.fetch = (async () => {
      fetchCalls += 1;
      return successfulJson({});
    }) as typeof globalThis.fetch;

    const error = await loginWithEmail({
      email: "alpha@example.com",
      password: "password123",
    }).catch((caught: unknown) => caught);

    expect(fetchCalls).toBe(0);
    expect(error).toBeInstanceOf(Error);
    expect((error as Error & { code?: string }).code).toBe(
      "captcha_unavailable",
    );
    expect((error as Error).message).not.toContain("Turnstile");
    expect((error as Error).message).not.toContain("Guest");
  });

  test("recovery CAPTCHA failure stops before the request is sent", async () => {
    process.env.NODE_ENV = "production";
    let fetchCalls = 0;
    globalThis.fetch = (async () => {
      fetchCalls += 1;
      return new Response(JSON.stringify({ accepted: true }), { status: 202 });
    }) as typeof globalThis.fetch;

    const error = await requestPasswordRecovery("alpha@example.com").catch(
      (caught: unknown) => caught,
    );

    expect(fetchCalls).toBe(0);
    expect(error).toBeInstanceOf(Error);
    expect((error as Error & { code?: string }).code).toBe(
      "captcha_unavailable",
    );
  });

  test("the recovery form surfaces a rejected request", () => {
    const recoveryForm = readFileSync(
      join(root, "app/auth/forgot-password/page.tsx"),
      "utf-8",
    );

    expect(recoveryForm).toContain('setStatus("error")');
    expect(recoveryForm).toContain('role="alert"');
    expect(recoveryForm).toContain('"auth.recovery.request_error"');
  });

  test("the direct real-auth recovery QA sends the shared local CAPTCHA token", () => {
    const qaHelper = readFileSync(
      join(root, "e2e/qa-248/helpers.ts"),
      "utf-8",
    );

    expect(qaHelper).toContain(
      'import { LOCAL_QA_CAPTCHA_TOKEN } from "../../lib/guest-captcha";',
    );
    expect(qaHelper).toContain(
      "data: { email, captcha_token: LOCAL_QA_CAPTCHA_TOKEN }",
    );
  });

  test("the existing auth form owns localized check-email and CAPTCHA errors", () => {
    const page = readFileSync(join(root, "app/page.tsx"), "utf-8");
    const form = readFileSync(
      join(root, "components/auth/AuthForm.tsx"),
      "utf-8",
    );
    const en = JSON.parse(
      readFileSync(join(root, "public/locales/en/common.json"), "utf-8"),
    );
    const es = JSON.parse(
      readFileSync(
        join(root, "public/locales/es-419/common.json"),
        "utf-8",
      ),
    );

    const submitHandler = page.slice(
      page.indexOf("const handleAuthSubmit"),
      page.indexOf("const isSignup"),
    );
    expect(submitHandler).toContain("needsEmailConfirmation");
    expect(submitHandler).toContain("NEXT_PUBLIC_E2E_ALLOW_MOCK_SIGNUP");
    expect(submitHandler).not.toContain("navigator.webdriver");
    expect(submitHandler).toContain("allowMockSignupNetwork");
    expect(submitHandler.indexOf("needsEmailConfirmation")).toBeLessThan(
      submitHandler.lastIndexOf("router.replace(postAuthPath())"),
    );
    expect(form).toContain('data-testid="auth-check-email"');
    expect(form).toContain("captcha_unavailable");
    expect(en.auth.signup.confirmation_title).toBe("Check your email");
    expect(en.auth.errors.captcha_unavailable).toBe(
      "This browser didn’t pass the security check. Open Cuadrao in a regular browser, or reload the page.",
    );
    expect(es.auth.signup.confirmation_title).toBe("Revisa tu correo");
    expect(es.auth.errors.captcha_unavailable).toBe(
      "Este navegador no pasó la verificación de seguridad. Abre Cuadrao en un navegador normal, o actualiza la página.",
    );
    expect(en.auth.errors.captcha_unavailable).not.toMatch(/try again/i);
    expect(es.auth.errors.captcha_unavailable).not.toMatch(/int[eé]ntalo de nuevo/i);
  });
});
