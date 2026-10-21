import { afterEach, describe, expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import {
  bootstrapGuest,
  cancelPendingGuestBootstrap,
  createGuestSessionBootstrapper,
  guestCaptchaPlanForEnvironment,
  guestCaptchaTokenForEnvironment,
  resetGuestBootstrapRuntime,
  startGuestSession,
} from "../lib/guest-session";
import { guestAccessEnabledFromEnv } from "../lib/private-alpha-flags";

const root = join(import.meta.dir, "..");
const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  resetGuestBootstrapRuntime();
});

describe("guest session entry contract", () => {
  test("defaults Guest presentation on and keeps explicit false as a kill switch", () => {
    expect(guestAccessEnabledFromEnv(undefined)).toBe(true);
    expect(guestAccessEnabledFromEnv("true")).toBe(true);
    expect(guestAccessEnabledFromEnv("false")).toBe(false);
    expect(guestAccessEnabledFromEnv(" OFF ")).toBe(false);
    expect(guestAccessEnabledFromEnv("invalid")).toBe(false);
  });

  test("keeps the auth landing and does not mount guest entry", () => {
    const page = readFileSync(join(root, "app/page.tsx"), "utf-8");

    expect(existsSync(join(root, "components/guest/GuestEntry.tsx"))).toBe(false);
    expect(page).not.toContain("<GuestEntry");
    expect(page).toContain("loginWithEmail");
    expect(page).toContain("signupWithEmail");
  });

  test("owns one idempotent bootstrap and fails closed without a production captcha", () => {
    const sessionPath = join(root, "lib/guest-session.ts");
    expect(existsSync(sessionPath)).toBe(true);
    if (!existsSync(sessionPath)) return;

    const session = readFileSync(sessionPath, "utf-8");
    const captcha = readFileSync(join(root, "lib/guest-captcha.ts"), "utf-8");
    expect(session).toContain("createGuestSessionBootstrapper");
    expect(captcha).toContain("production");
    expect(captcha).toContain("CAPTCHA");
    expect(captcha).toContain(
      "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit",
    );
    expect(captcha).toContain("turnstile.render");
    expect(captcha).toContain('"error-callback"');
    expect(session).not.toContain("signInAnonymously");
    expect(session).not.toContain("service_role");
  });

  test("coalesces concurrent bootstrap calls and retries only after failure", async () => {
    let calls = 0;
    const bootstrapper = createGuestSessionBootstrapper(
      async (value: string) => {
        calls += 1;
        if (value === "fail") throw new Error("failed");
        return value;
      },
    );

    const first = bootstrapper.run("guest");
    const duplicate = bootstrapper.run("ignored");
    expect(await first).toBe("guest");
    expect(await duplicate).toBe("guest");
    expect(calls).toBe(1);

    bootstrapper.reset();
    await expect(bootstrapper.run("fail")).rejects.toThrow("failed");
    expect(await bootstrapper.run("recovered")).toBe("recovered");
    expect(calls).toBe(3);
  });

  test("an aborted bootstrap catch does not clear its replacement", async () => {
    let rejectFirst!: (error: Error) => void;
    let secondCalls = 0;
    const bootstrapper = createGuestSessionBootstrapper(
      async (value: string) => {
        if (value === "first") {
          return new Promise<string>((_resolve, reject) => {
            rejectFirst = reject;
          });
        }
        secondCalls += 1;
        return value;
      },
    );

    const first = bootstrapper.run("first");
    bootstrapper.reset();
    const second = bootstrapper.run("second");
    rejectFirst(Object.assign(new Error("aborted"), { name: "AbortError" }));
    await expect(first).rejects.toMatchObject({ name: "AbortError" });
    expect(await second).toBe("second");
    expect(secondCalls).toBe(1);
    expect(await bootstrapper.run("ignored")).toBe("second");
    expect(secondCalls).toBe(1);
  });

  test("allows an explicit production-QA CAPTCHA token only for loopback", () => {
    expect(
      guestCaptchaTokenForEnvironment({
        nodeEnv: "production",
        apiUrl: "http://localhost:8000/api/v1",
        localQaToken: "local-qa-proof",
      }),
    ).toBe("local-qa-proof");
    expect(
      guestCaptchaTokenForEnvironment({
        nodeEnv: "production",
        apiUrl: "https://api.argus.example/api/v1",
        localQaToken: "local-qa-proof",
      }),
    ).toBeNull();
  });

  test("keeps ordinary production closed and development deterministic", () => {
    expect(
      guestCaptchaTokenForEnvironment({
        nodeEnv: "production",
        apiUrl: "http://localhost:8000/api/v1",
        localQaToken: "",
      }),
    ).toBeNull();
    expect(
      guestCaptchaTokenForEnvironment({
        nodeEnv: "development",
        apiUrl: "http://localhost:8000/api/v1",
        localQaToken: "",
      }),
    ).toBe("argus-local-browser-qa");
  });

  test.each([
    [" cuadrao-key ", "argus-key", "cuadrao-key"],
    [undefined, "argus-key", "argus-key"],
    ["   ", "argus-key", "argus-key"],
    ["cuadrao-key", undefined, "cuadrao-key"],
    [undefined, undefined, undefined],
    [" ", " ", undefined],
  ])("resolves canonical and legacy site keys (%s, %s)", (canonical, legacy, expected) => {
    expect(guestCaptchaPlanForEnvironment({
      nodeEnv: "production",
      apiUrl: "https://api.argus.example/api/v1",
      localQaToken: undefined,
      cuadraoTurnstileSiteKey: canonical,
      turnstileSiteKey: legacy,
    })).toEqual(expected ? { kind: "turnstile", siteKey: expected } : { kind: "unavailable" });
  });

  test("acquires a production Turnstile challenge instead of failing guest entry", () => {
    expect(
      guestCaptchaPlanForEnvironment({
        nodeEnv: "production",
        apiUrl: "https://api.argus.example/api/v1",
        localQaToken: "",
        turnstileSiteKey: "public-site-key",
      }),
    ).toEqual({
      kind: "turnstile",
      siteKey: "public-site-key",
    });
    expect(
      guestCaptchaPlanForEnvironment({
        nodeEnv: "production",
        apiUrl: "https://api.argus.example/api/v1",
        localQaToken: "",
        turnstileSiteKey: "",
      }),
    ).toEqual({ kind: "unavailable" });
    expect(
      guestCaptchaTokenForEnvironment({
        nodeEnv: "production",
        apiUrl: "https://api.argus.example/api/v1",
        localQaToken: "",
        browserCaptchaToken: "verified-turnstile-token",
      }),
    ).toBe("verified-turnstile-token");
  });

  test("uses the existing server guest endpoint and persists the provider session", () => {
    const api = readFileSync(join(root, "lib/argus-api.ts"), "utf-8");
    const session = readFileSync(join(root, "lib/guest-session.ts"), "utf-8");
    const captcha = readFileSync(join(root, "lib/guest-captcha.ts"), "utf-8");

    expect(session).toContain("export async function bootstrapGuest");
    expect(session).toContain('"/auth/guest"');
    expect(session).toContain("attributionBody");
    expect(session).toContain("persistBrowserSession(response)");
    expect(session).toContain("cancelPendingGuestBootstrap");
    expect(session).toContain("persistGuestBootstrap");
    expect(session).toContain("guestBootstrapAbort?.abort()");
    expect(session).toContain("const signal = guestBootstrapAbort?.signal");
    expect(session).toContain("if (pending === started) pending = null");
    expect(session).toContain("acquireGuestCaptchaToken");
    expect(session).toContain("if (signal?.aborted || !persistGuestBootstrap)");
    expect(session).not.toContain("signal: guestBootstrapAbort?.signal");
    expect(captcha).toContain("signal?: AbortSignal");
    expect(captcha).toContain("Guest CAPTCHA cancelled.");
    expect(session.indexOf("if (!persistGuestBootstrap)")).toBeLessThan(
      session.lastIndexOf("persistBrowserSession(response)"),
    );
    expect(api).toContain("if (error)");
  });

  test("guest presentation no longer owns a chat route", () => {
    const page = readFileSync(join(root, "app/page.tsx"), "utf-8");

    expect(existsSync(join(root, "components/guest/GuestEntry.tsx"))).toBe(false);
    expect(existsSync(join(root, "app/chat/page.tsx"))).toBe(false);
    expect(page).not.toContain("currentChatPath()");
    expect(page).not.toContain("startGuestSession");
  });

  test("registers an active guest through a prepared signup handoff", () => {
    const guestApi = readFileSync(join(root, "lib/guest-api.ts"), "utf-8");

    expect(guestApi).toContain("registerGuestAccount");
    expect(guestApi).toContain('handoff_kind: "new_account_signup"');
    expect(guestApi).toContain('"/auth/guest/signup"');
    expect(guestApi).toContain("persistBrowserSession(response)");
    expect(guestApi).not.toContain('"/auth/guest/link"');
  });

  test("cancel aborts the in-flight guest fetch so late cookies cannot land", async () => {
    let seen: AbortSignal | undefined;
    globalThis.fetch = (async (_input, init) => {
      seen = init?.signal;
      return new Promise((_resolve, reject) => {
        const abort = () =>
          reject(Object.assign(new Error("aborted"), { name: "AbortError" }));
        if (init?.signal?.aborted) {
          abort();
          return;
        }
        init?.signal?.addEventListener("abort", abort, { once: true });
      });
    }) as typeof fetch;

    const pending = startGuestSession("en", "token");
    for (let i = 0; i < 20 && !seen; i += 1) {
      await Promise.resolve();
    }
    expect(seen).toBeDefined();
    expect(seen?.aborted).toBe(false);
    cancelPendingGuestBootstrap();
    expect(seen?.aborted).toBe(true);
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });

  test("bootstrapGuest stays bound to its request signal after a restart", async () => {
    const fetches: AbortSignal[] = [];
    globalThis.fetch = (async (_input, init) => {
      if (init?.signal) fetches.push(init.signal);
      return new Response(
        JSON.stringify({ authenticated: true, account_kind: "guest" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }) as typeof fetch;

    await expect(startGuestSession("en", "live-token")).resolves.toMatchObject({
      account_kind: "guest",
    });
    expect(fetches).toHaveLength(1);

    const stale = new AbortController();
    stale.abort();
    await expect(
      bootstrapGuest({
        captcha_token: "stale-token",
        language: "en",
        signal: stale.signal,
      }),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(fetches).toHaveLength(1);

    const owned = new AbortController();
    await bootstrapGuest({
      captcha_token: "owned-token",
      language: "en",
      signal: owned.signal,
    });
    expect(fetches).toHaveLength(2);
    expect(fetches[1]).toBe(owned.signal);
  });
});
