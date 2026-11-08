import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

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
    });

    expect(body).toMatchObject({
      email: "alpha@example.com",
      captcha_token: "argus-local-browser-qa",
    });
    expect(result.response.session).toBeNull();
    expect(result.needsEmailConfirmation).toBe(true);
  });

  test("a login request that never returns ends as a browser-check failure", async () => {
    globalThis.fetch = (() => new Promise(() => undefined)) as typeof fetch;

    const result = await Promise.race([
      loginWithEmail(
        { email: "alpha@example.com", password: "password123" },
        { requestTimeoutMs: 30 },
      ).then(() => "resolved", (error: unknown) => error),
      new Promise<string>((resolve) => setTimeout(() => resolve("hung"), 200)),
    ]);

    expect(result).toMatchObject({ code: "captcha_unavailable" });
    expect(result).not.toMatchObject({ code: "unauthorized" });
  });

  test("a rejected login from the server is classified as unauthorized", async () => {
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify({
          code: "unauthorized",
          detail: "Invalid email or password.",
        }),
        { status: 401, headers: { "Content-Type": "application/json" } },
      )) as typeof fetch;

    const error = await loginWithEmail({
      email: "alpha@example.com",
      password: "password123",
    }).catch((caught: unknown) => caught);

    expect(error).toMatchObject({ code: "unauthorized" });
    expect(error).not.toMatchObject({ code: "captcha_unavailable" });
  });

  test("signup with a returned session preserves the authenticated outcome", async () => {
    globalThis.fetch = (async () =>
      successfulJson({ user: { id: "user-1" }, session: {} })) as typeof fetch;

    const result = await signupWithEmail({
      email: "alpha@example.com",
      password: "password123",
      language: "en",
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

  const TURNSTILE_RETRY_CHILD = "AUTH_CAPTCHA_TURNSTILE_HERMETIC_CHILD";
  const TURNSTILE_CHILD_COMPLETION_SENTINEL =
    "AUTH_CAPTCHA_TURNSTILE_HERMETIC_CHILD_COMPLETE:v1:renders=2:callbacks=2:posts=2";
  const TURNSTILE_CHILD_EXPECTED_RAN_TEST_COUNT = 1;

  async function assertProductionAuthModuleProvenance() {
    const libDir = join(import.meta.dir, "..", "lib");
    const guestCaptchaPath = fileURLToPath(
      new URL(await import.meta.resolve("../lib/guest-captcha.ts"), import.meta.url),
    );
    const argusApiPath = fileURLToPath(
      new URL(await import.meta.resolve("../lib/argus-api.ts"), import.meta.url),
    );
    const passwordAuthPath = fileURLToPath(
      new URL(
        await import.meta.resolve("../lib/password-auth-request.ts"),
        import.meta.url,
      ),
    );
    expect(guestCaptchaPath).toBe(join(libDir, "guest-captcha.ts"));
    expect(argusApiPath).toBe(join(libDir, "argus-api.ts"));
    expect(passwordAuthPath).toBe(join(libDir, "password-auth-request.ts"));
  }

  async function exerciseTurnstileRetryProofInProcess() {
    const issuanceTokens = [
      "mocked-turnstile-proof-one",
      "mocked-turnstile-proof-two",
    ] as const;
    let renderCalls = 0;
    const callbackTokens: string[] = [];
    const bodies: Array<Record<string, unknown>> = [];
    const loginPosts: Array<{ method: string; pathname: string }> = [];
    const originalNodeEnv = process.env.NODE_ENV;
    const originalApiUrl = process.env.NEXT_PUBLIC_ARGUS_API_URL;
    const originalCuadraoSiteKey =
      process.env.NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY;
    const originalTurnstileSiteKey =
      process.env.NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY;
    const originalLocalToken =
      process.env.NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN;
    const originalCuadraoLocalToken =
      process.env.NEXT_PUBLIC_CUADRAO_LOCAL_QA_CAPTCHA_TOKEN;
    const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;

    await assertProductionAuthModuleProvenance();

    GlobalRegistrator.register({ url: "https://app.example.test/login" });
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
      true;
    const previousTurnstile = window.turnstile;

    process.env.NODE_ENV = "production";
    process.env.NEXT_PUBLIC_ARGUS_API_URL = "https://api.example.test/api/v1";
    process.env.NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY = "test-site-key";
    delete process.env.NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY;
    delete process.env.NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN;
    delete process.env.NEXT_PUBLIC_CUADRAO_LOCAL_QA_CAPTCHA_TOKEN;
    delete process.env.NEXT_PUBLIC_MOCK_AUTH;

    window.turnstile = {
      render(_container, options) {
        renderCalls += 1;
        const token =
          issuanceTokens[renderCalls - 1] ?? issuanceTokens[issuanceTokens.length - 1];
        queueMicrotask(() => {
          callbackTokens.push(token);
          options.callback(token);
        });
        return `widget-${renderCalls}`;
      },
      remove() {},
    };

    globalThis.fetch = (async (input, init) => {
      const url = new URL(String(input), process.env.NEXT_PUBLIC_ARGUS_API_URL);
      if (url.pathname.endsWith("/auth/login")) {
        loginPosts.push({
          method: (init?.method ?? "GET").toUpperCase(),
          pathname: url.pathname,
        });
      }
      bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
      return new Response(
        JSON.stringify({
          code: "unauthorized",
          detail: "Invalid email or password.",
        }),
        { status: 401, headers: { "Content-Type": "application/json" } },
      );
    }) as typeof globalThis.fetch;

    try {
      for (let attempt = 0; attempt < 2; attempt += 1) {
        await loginWithEmail({
          email: "alpha@example.com",
          password: "password123",
        }).catch(() => undefined);
      }

      expect(renderCalls).toBe(2);
      expect(callbackTokens).toEqual([...issuanceTokens]);
      expect(loginPosts).toEqual([
        { method: "POST", pathname: "/api/v1/auth/login" },
        { method: "POST", pathname: "/api/v1/auth/login" },
      ]);
      expect(bodies).toHaveLength(2);
      expect(bodies[0]?.captcha_token).toBe(issuanceTokens[0]);
      expect(bodies[1]?.captcha_token).toBe(issuanceTokens[1]);
      process.stdout.write(`${TURNSTILE_CHILD_COMPLETION_SENTINEL}\n`);
    } finally {
      globalThis.fetch = originalFetch;
      if (previousTurnstile === undefined) {
        delete window.turnstile;
      } else {
        window.turnstile = previousTurnstile;
      }
      document.body.innerHTML = "";
      await GlobalRegistrator.unregister();
      process.env.NODE_ENV = originalNodeEnv;
      if (originalApiUrl === undefined) {
        delete process.env.NEXT_PUBLIC_ARGUS_API_URL;
      } else {
        process.env.NEXT_PUBLIC_ARGUS_API_URL = originalApiUrl;
      }
      if (originalCuadraoSiteKey === undefined) {
        delete process.env.NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY;
      } else {
        process.env.NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY = originalCuadraoSiteKey;
      }
      if (originalTurnstileSiteKey === undefined) {
        delete process.env.NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY;
      } else {
        process.env.NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY = originalTurnstileSiteKey;
      }
      if (originalLocalToken === undefined) {
        delete process.env.NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN;
      } else {
        process.env.NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN = originalLocalToken;
      }
      if (originalCuadraoLocalToken === undefined) {
        delete process.env.NEXT_PUBLIC_CUADRAO_LOCAL_QA_CAPTCHA_TOKEN;
      } else {
        process.env.NEXT_PUBLIC_CUADRAO_LOCAL_QA_CAPTCHA_TOKEN =
          originalCuadraoLocalToken;
      }
      if (originalMockAuth === undefined) {
        delete process.env.NEXT_PUBLIC_MOCK_AUTH;
      } else {
        process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
      }
    }
  }

  test("each login attempt calls the Turnstile issuance interface twice and submits each returned token", async () => {
    const hermeticChild = process.env[TURNSTILE_RETRY_CHILD] === "1";
    if (!hermeticChild) {
      const webRoot = join(import.meta.dir, "..");
      const result = Bun.spawnSync({
        cmd: [
          process.execPath,
          "test",
          import.meta.path,
          "--test-name-pattern",
          "each login attempt calls the Turnstile issuance interface twice",
        ],
        cwd: webRoot,
        env: { ...process.env, [TURNSTILE_RETRY_CHILD]: "1" },
        stdout: "pipe",
        stderr: "pipe",
      });
      const output = `${result.stdout.toString()}${result.stderr.toString()}`;
      expect(result.exitCode).toBe(0);
      expect(output).toContain(TURNSTILE_CHILD_COMPLETION_SENTINEL);
      expect(output).toMatch(
        new RegExp(
          `Ran ${TURNSTILE_CHILD_EXPECTED_RAN_TEST_COUNT} test(?:s)? across 1 file`,
        ),
      );
      expect(output).toMatch(
        new RegExp(` ${TURNSTILE_CHILD_EXPECTED_RAN_TEST_COUNT} pass`),
      );
      expect(output).toMatch(/ 0 fail/);
      expect(output).toMatch(
        /\(pass\) password auth CAPTCHA and confirmation contract > each login attempt calls the Turnstile issuance interface twice/,
      );
      return;
    }
    await exerciseTurnstileRetryProofInProcess();
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
    const page = readFileSync(join(root, "app/auth/forgot-password/page.tsx"), "utf-8");
    const recoveryForm = readFileSync(
      join(root, "components/auth/RecoveryRequest.tsx"),
      "utf-8",
    );

    expect(page).toContain("<RecoveryRequest />");
    expect(recoveryForm).toContain('setState("error")');
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
