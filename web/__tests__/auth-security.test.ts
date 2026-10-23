import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import {
  accountSecurityLoadFailureAction,
  createAuthSecurityActions,
  readValidatedAuthSession,
  type AuthSecurityPort,
} from "../lib/auth-security";
import { STORAGE_REGISTRY } from "../lib/browser-storage";
import { synchronizeCurrentBrowserLogout } from "../lib/argus-api";
import {
  handleRecoveryRequest,
  RecoveryCaptchaRejectedError,
  RecoveryAttemptLimiter,
  recoveryRedirectTarget,
} from "../lib/recovery-request";

function authPort(options?: {
  exchangeError?: Error;
  redirectType?: string | null;
  updateError?: Error;
  signOutError?: Error;
}) {
  const exchangedCodes: string[] = [];
  const updates: Array<Record<string, string>> = [];
  const scopes: string[] = [];
  const auth: AuthSecurityPort = {
    async exchangeCodeForSession(code) {
      exchangedCodes.push(code);
      return {
        data: { redirectType: options?.redirectType === undefined ? "recovery" : options.redirectType },
        error: options?.exchangeError ?? null,
      };
    },
    async updateUser(attributes) {
      updates.push(attributes);
      return { error: options?.updateError ?? null };
    },
    async signOut({ scope }) {
      scopes.push(scope);
      return { error: options?.signOutError ?? null };
    },
    async getValidatedSession() {
      return { userId: "person-1", sessionId: "session-1" };
    },
  };
  return { auth, exchangedCodes, updates, scopes };
}

function recoveryStore() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
}

describe("account security actions", () => {
  test("validated provider identity distinguishes ended sessions from outages", async () => {
    const claims = { data: { claims: { sub: "person-1", session_id: "session-1" } }, error: null };
    const user = { data: { user: { id: "person-1" } }, error: null };
    expect(await readValidatedAuthSession({ getClaims: async () => claims, getUser: async () => user }))
      .toEqual({ userId: "person-1", sessionId: "session-1" });
    expect(await readValidatedAuthSession({ getClaims: async () => ({ data: null, error: null }), getUser: async () => user }))
      .toBeNull();
    expect(await readValidatedAuthSession({ getClaims: async () => claims,
      getUser: async () => ({ data: { user: null }, error: { status: 401, code: "bad_jwt" } }) }))
      .toBeNull();
    const unavailable = { status: 503, code: "unexpected_failure" };
    expect(readValidatedAuthSession({ getClaims: async () => claims,
      getUser: async () => ({ data: { user: null }, error: unavailable }) })).rejects.toBe(unavailable);
  });

  test("a transient identity outage leaves recovery proof and global retry intact", async () => {
    const port = authPort();
    const store = recoveryStore();
    const actions = createAuthSecurityActions(port.auth, async () => undefined, store);
    await actions.exchangeRecoveryCode("one-time-code");
    port.auth.getValidatedSession = async () => { throw new Error("network unavailable"); };
    expect(await actions.hasRecoverySession()).toBe(false);
    expect(store.getItem("cuadrao:recovery-session:v1")).toBeTruthy();
    const result = await actions.signOutAllSessions();
    expect(result.revocation).toBe("failed");
    expect(result.revocationAuthority).toBe("unknown");
    expect(result.cookieSync).toBe("not_required");
    expect(port.scopes).toEqual([]);
    port.auth.getValidatedSession = async () => ({ userId: "person-1", sessionId: "session-1" });
    expect(await actions.hasRecoverySession()).toBe(true);
  });

  test("an ordinary signed-in session cannot enter recovery or reset its password", async () => {
    const port = authPort();
    port.auth.hasSession = async () => true;
    const actions = createAuthSecurityActions(port.auth, async () => undefined, recoveryStore());

    expect(await actions.hasRecoverySession()).toBe(false);
    expect(actions.resetRecoveredPassword("new-password")).rejects.toThrow();
    expect(port.updates).toEqual([]);
  });

  test("a successful non-recovery PKCE exchange cannot authorize password reset", async () => {
    const port = authPort({ redirectType: null });
    const actions = createAuthSecurityActions(port.auth, async () => undefined, recoveryStore());

    expect(actions.exchangeRecoveryCode("ordinary-code")).rejects.toThrow();
    expect(await actions.hasRecoverySession()).toBe(false);
    expect(port.updates).toEqual([]);
  });

  test("a verified recovery session survives reload but another session cannot reuse its proof", async () => {
    const port = authPort();
    const store = recoveryStore();
    const firstPage = createAuthSecurityActions(port.auth, async () => undefined, store);
    await firstPage.exchangeRecoveryCode("one-time-code");

    const marker = store.getItem("cuadrao:recovery-session:v1");
    expect(marker).toBeTruthy();
    expect(marker).not.toContain("session-1");
    expect(STORAGE_REGISTRY["cuadrao:recovery-session:v1"]).toBe("temporary");
    const reloadedPage = createAuthSecurityActions(port.auth, async () => undefined, store);
    expect(await reloadedPage.hasRecoverySession()).toBe(true);

    port.auth.getValidatedSession = async () => ({ userId: "person-1", sessionId: "session-2" });
    expect(await reloadedPage.hasRecoverySession()).toBe(false);
    port.auth.getValidatedSession = async () => ({ userId: "person-1", sessionId: "session-1" });
    expect(await reloadedPage.hasRecoverySession()).toBe(false);
  });

  test("a failed or reused code removes an older recovery proof", async () => {
    const port = authPort();
    const actions = createAuthSecurityActions(port.auth, async () => undefined, recoveryStore());
    await actions.exchangeRecoveryCode("first-code");
    expect(await actions.hasRecoverySession()).toBe(true);

    port.auth.exchangeCodeForSession = async () => ({ error: new Error("used") });
    expect(actions.exchangeRecoveryCode("used-code")).rejects.toThrow();
    expect(await actions.hasRecoverySession()).toBe(false);
  });

  test("blocked browser storage fails recovery closed", async () => {
    const port = authPort();
    const denied = {
      getItem: () => { throw new Error("storage denied"); },
      setItem: () => { throw new Error("storage denied"); },
      removeItem: () => { throw new Error("storage denied"); },
    };
    const actions = createAuthSecurityActions(port.auth, async () => undefined, denied);

    expect(actions.exchangeRecoveryCode("one-time-code")).rejects.toThrow();
    expect(await actions.hasRecoverySession()).toBe(false);
    expect(port.updates).toEqual([]);
  });

  test("a failed global revoke retains provider and cookie proof for retry", async () => {
    const port = authPort({ signOutError: new Error("provider unavailable") });
    let cookieClears = 0;
    const actions = createAuthSecurityActions(port.auth, async () => { cookieClears += 1; }, recoveryStore());

    const failed = await actions.signOutAllSessions();
    expect(failed.revocation).toBe("failed");
    expect(failed.cookieSync).toBe("not_required");
    expect(cookieClears).toBe(0);
    expect(port.scopes).toEqual(["global"]);
  });

  test("global revoke cannot claim success when its provider session has ended", async () => {
    const port = authPort();
    port.auth.getValidatedSession = async () => null;
    let cookieClears = 0;
    const actions = createAuthSecurityActions(port.auth, async () => { cookieClears += 1; }, recoveryStore());

    const result = await actions.signOutAllSessions();
    expect(result.revocation).toBe("failed");
    expect(result.cookieSync).toBe("not_required");
    expect(result.freshLoginRequired).toBe(false);
    expect(result.revocationAuthority).toBe("absent");
    expect(port.scopes).toEqual([]);
    expect(cookieClears).toBe(0);
  });

  test("recovery proof clears only after successful local or global sign-out", async () => {
    for (const scope of ["local", "global"] as const) {
      const port = authPort();
      const store = recoveryStore();
      const actions = createAuthSecurityActions(port.auth, async () => undefined, store);
      await actions.exchangeRecoveryCode("one-time-code");
      const result = scope === "local" ? await actions.signOutThisBrowser() : await actions.signOutAllSessions();
      expect(result.revocation).toBe("complete");
      expect(store.getItem("cuadrao:recovery-session:v1")).toBeNull();
    }
  });
  test("the recovery page is the only owner of the PKCE code exchange", () => {
    const browserClient = readFileSync(
      join(import.meta.dir, "../lib/supabase-client.ts"),
      "utf-8",
    );
    const recoveryPage = readFileSync(
      join(import.meta.dir, "../components/auth/RecoveryReset.tsx"),
      "utf-8",
    );

    expect(browserClient).toContain("detectSessionInUrl: false");
    expect(recoveryPage).toContain(".exchangeRecoveryCode(code)");
    const codeRead = recoveryPage.indexOf('.get("code")');
    const queryRemoved = recoveryPage.indexOf(
      'window.history.replaceState(null, "", window.location.pathname)',
    );
    const codeExchange = recoveryPage.indexOf(".exchangeRecoveryCode(code)");
    expect(codeRead).toBeGreaterThan(-1);
    expect(queryRemoved).toBeGreaterThan(codeRead);
    expect(codeExchange).toBeGreaterThan(queryRemoved);
  });

  test("partial revoke-all outcomes stay honest and retryable in both password flows", () => {
    const accountPage = readFileSync(
      join(import.meta.dir, "../components/auth/AccountSecurity.tsx"),
      "utf-8",
    );
    const recoveryPage = readFileSync(
      join(import.meta.dir, "../components/auth/RecoveryReset.tsx"),
      "utf-8",
    );

    expect(accountPage).toContain('result.revocation === "failed"');
    expect(accountPage).toContain(
      '"account_security.password.revocation_warning"',
    );
    expect(recoveryPage).toContain('result.revocation === "failed"');
    expect(recoveryPage).toContain('"auth.recovery.retry_revocation"');
    expect(recoveryPage).toContain('"auth.recovery.password_rejected"');
  });

  test("ordinary logout keeps provider failure retryable while still clearing Argus cookies", async () => {
    const scopes: string[] = [];
    let cookieClears = 0;

    const result = await synchronizeCurrentBrowserLogout(
      async () => {
        scopes.push("local");
        return { error: new Error("provider unavailable") };
      },
      async () => {
        cookieClears += 1;
        return { success: true };
      },
    );

    expect(scopes).toEqual(["local"]);
    expect(cookieClears).toBe(1);
    expect(result).toEqual({
      revocation: "failed",
      cookieSync: "cleared",
    });
  });

  test("ordinary logout reports cookie failure after provider revocation succeeds", async () => {
    const result = await synchronizeCurrentBrowserLogout(
      async () => ({ error: null }),
      async () => {
        throw new Error("cookie bridge unavailable");
      },
    );

    expect(result).toEqual({
      revocation: "complete",
      cookieSync: "failed",
    });
  });

  test("ordinary logout still starts cookie cleanup when auth lookup throws", async () => {
    let cookieClears = 0;

    const result = await synchronizeCurrentBrowserLogout(
      async () => {
        throw new Error("Supabase client unavailable");
      },
      async () => {
        cookieClears += 1;
        return { success: true };
      },
    );

    expect(cookieClears).toBe(1);
    expect(result).toEqual({
      revocation: "failed",
      cookieSync: "cleared",
    });
  });

  test("account security sends an ended session to login, a refusal to the closed state, and a 503 to the server screen", () => {
    expect(accountSecurityLoadFailureAction({ status: 401 })).toBe(
      "redirect_to_login",
    );
    expect(accountSecurityLoadFailureAction({ status: 403 })).toBe("closed");
    expect(accountSecurityLoadFailureAction({ status: 503 })).toBe("server");
    expect(accountSecurityLoadFailureAction(new Error("network unavailable"))).toBe(
      "retry",
    );
  });

  test("normal password change proves the current password and requires a fresh login", async () => {
    const port = authPort();
    let cookieClears = 0;
    const actions = createAuthSecurityActions(port.auth, async () => {
      cookieClears += 1;
    });

    const result = await actions.changePassword({
      currentPassword: "old-password",
      newPassword: "new-password",
    });

    expect(port.updates).toEqual([
      { password: "new-password", current_password: "old-password" },
    ]);
    expect(port.scopes).toEqual(["global"]);
    expect(cookieClears).toBe(1);
    expect(result).toEqual({
      currentSessionPreserved: false,
      freshLoginRequired: true,
      revocation: "complete",
      cookieSync: "cleared",
    });
  });

  test("the change path is one native provider update with no sign-in verification", () => {
    const source = readFileSync(
      join(import.meta.dir, "../lib/auth-security.ts"),
      "utf-8",
    );
    expect(source).toContain("current_password");
    expect(source).not.toContain("signInWithPassword");
  });

  test("a rejected current password leaves the session and cookies untouched", async () => {
    const port = authPort({
      updateError: new Error("Current password required when setting new password."),
    });
    let cookieClears = 0;
    const actions = createAuthSecurityActions(port.auth, async () => {
      cookieClears += 1;
    });

    expect(
      actions.changePassword({
        currentPassword: "wrong-password",
        newPassword: "new-password",
      }),
    ).rejects.toThrow();
    expect(port.updates).toEqual([
      { password: "new-password", current_password: "wrong-password" },
    ]);
    expect(port.scopes).toEqual([]);
    expect(cookieClears).toBe(0);
  });

  test("normal password change reports a successful update when revoke-all fails", async () => {
    const port = authPort({ signOutError: new Error("provider unavailable") });
    let cookieClears = 0;
    const actions = createAuthSecurityActions(port.auth, async () => {
      cookieClears += 1;
    });

    const result = await actions.changePassword({
      currentPassword: "old-password",
      newPassword: "new-password",
    });

    expect(port.updates).toEqual([
      { password: "new-password", current_password: "old-password" },
    ]);
    expect(port.scopes).toEqual(["global"]);
    expect(cookieClears).toBe(0);
    expect(result).toEqual({
      currentSessionPreserved: "unknown",
      freshLoginRequired: false,
      revocation: "failed",
      cookieSync: "not_required",
      revocationAuthority: "present",
    });
  });

  test("recovery exchanges one code before changing the password", async () => {
    const port = authPort();
    const actions = createAuthSecurityActions(port.auth, async () => undefined, recoveryStore());

    await actions.exchangeRecoveryCode("one-time-code");
    const result = await actions.resetRecoveredPassword("new-password");

    expect(port.exchangedCodes).toEqual(["one-time-code"]);
    expect(port.updates).toEqual([{ password: "new-password" }]);
    expect(port.scopes).toEqual(["global"]);
    expect(result.freshLoginRequired).toBe(true);
  });

  test("recovery reports a successful update when revoke-all fails", async () => {
    const port = authPort({ signOutError: new Error("provider unavailable") });
    const store = recoveryStore();
    const actions = createAuthSecurityActions(port.auth, async () => undefined, store);

    await actions.exchangeRecoveryCode("one-time-code");
    const result = await actions.resetRecoveredPassword("new-password");

    expect(port.updates).toEqual([{ password: "new-password" }]);
    expect(port.scopes).toEqual(["global"]);
    expect(result.revocation).toBe("failed");
    expect(result.freshLoginRequired).toBe(false);
    expect(await createAuthSecurityActions(port.auth, async () => undefined, store).hasRecoverySession()).toBe(false);
    port.auth.signOut = async ({ scope }) => { port.scopes.push(scope); return { error: null }; };
    const retry = await actions.signOutAllSessions();
    expect(retry.revocation).toBe("complete");
    expect(port.scopes).toEqual(["global", "global"]);
  });

  test("an invalid or reused recovery code cannot change a password", async () => {
    const port = authPort({ exchangeError: new Error("expired") });
    const actions = createAuthSecurityActions(port.auth, async () => undefined);

    expect(actions.exchangeRecoveryCode("reused-code")).rejects.toThrow();
    expect(port.updates).toEqual([]);
    expect(port.scopes).toEqual([]);
  });

  test("signing out other sessions preserves this browser and its cookies", async () => {
    const port = authPort();
    let cookieClears = 0;
    const actions = createAuthSecurityActions(port.auth, async () => {
      cookieClears += 1;
    });

    const result = await actions.signOutOtherSessions();

    expect(port.scopes).toEqual(["others"]);
    expect(cookieClears).toBe(0);
    expect(result).toEqual({
      currentSessionPreserved: true,
      freshLoginRequired: false,
      revocation: "complete",
      cookieSync: "not_required",
    });
  });

  test("signing out this browser uses only the local scope", async () => {
    const port = authPort();
    let cookieClears = 0;
    const actions = createAuthSecurityActions(port.auth, async () => {
      cookieClears += 1;
    });

    const result = await actions.signOutThisBrowser();

    expect(port.scopes).toEqual(["local"]);
    expect(cookieClears).toBe(1);
    expect(result.freshLoginRequired).toBe(true);
  });

  test("a revoke-others provider failure does not claim success", async () => {
    const port = authPort({ signOutError: new Error("backend unavailable") });
    let cookieClears = 0;
    const actions = createAuthSecurityActions(port.auth, async () => {
      cookieClears += 1;
    });

    expect(actions.signOutOtherSessions()).rejects.toThrow();
    expect(port.scopes).toEqual(["others"]);
    expect(cookieClears).toBe(0);
  });

  test("global sign out reports partial cleanup without claiming cookie sync", async () => {
    const port = authPort();
    const actions = createAuthSecurityActions(port.auth, async () => {
      throw new Error("backend unavailable");
    });

    const result = await actions.signOutAllSessions();

    expect(port.scopes).toEqual(["global"]);
    expect(result).toEqual({
      currentSessionPreserved: false,
      freshLoginRequired: true,
      revocation: "complete",
      cookieSync: "failed",
    });
  });
});

describe("recovery request safety", () => {
  test("production recovery uses one configured origin and rejects another", () => {
    expect(
      recoveryRedirectTarget({
        requestUrl: "https://app.argus.example/api/auth/recovery",
        requestOrigin: "https://app.argus.example",
        configuredAppOrigin: "https://app.argus.example",
        environment: "production",
      }),
    ).toBe("https://app.argus.example/auth/recovery");
    expect(
      recoveryRedirectTarget({
        requestUrl: "https://app.argus.example/api/auth/recovery",
        requestOrigin: "https://attacker.example",
        configuredAppOrigin: "https://app.argus.example",
        environment: "production",
      }),
    ).toBeNull();
    expect(
      recoveryRedirectTarget({
        requestUrl: "http://app.argus.example/api/auth/recovery",
        requestOrigin: "http://app.argus.example",
        configuredAppOrigin: "http://app.argus.example",
        environment: "production",
      }),
    ).toBeNull();
  });

  test("production recovery reports missing origin configuration as unavailable", async () => {
    const response = await handleRecoveryRequest(
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
        },
        body: JSON.stringify({ email: "person@example.com" }),
      }),
      {
        configuredAppOrigin: undefined,
        environment: "production",
        limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
        globalLimiter: new RecoveryAttemptLimiter({
          limit: 100,
          windowMs: 60_000,
        }),
        async sendRecovery() {
          throw new Error("must not send without a configured origin");
        },
      },
    );

    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ accepted: false });
  });

  test("local recovery allows only the documented local origins", () => {
    expect(
      recoveryRedirectTarget({
        requestUrl: "http://localhost:3000/api/auth/recovery",
        requestOrigin: "http://localhost:3000",
        configuredAppOrigin: undefined,
        environment: "development",
      }),
    ).toBe("http://localhost:3000/auth/recovery");
    expect(
      recoveryRedirectTarget({
        requestUrl: "http://evil.local:3000/api/auth/recovery",
        requestOrigin: "http://evil.local:3000",
        configuredAppOrigin: undefined,
        environment: "development",
      }),
    ).toBeNull();
  });

  test("rate limiting applies independently to normalized email and address", () => {
    let now = 1_000;
    const limiter = new RecoveryAttemptLimiter({
      limit: 2,
      windowMs: 1_000,
      now: () => now,
    });

    expect(limiter.retryAfterMs(["email:user@example.com", "ip:127.0.0.1"])).toBe(0);
    expect(limiter.retryAfterMs(["email:user@example.com", "ip:127.0.0.2"])).toBe(0);
    expect(limiter.retryAfterMs(["email:user@example.com", "ip:127.0.0.3"])).toBe(1_000);
    now = 2_001;
    expect(limiter.retryAfterMs(["email:user@example.com", "ip:127.0.0.3"])).toBe(0);
  });

  test("rate limiting bounds active unique-key churn", () => {
    const limiter = new RecoveryAttemptLimiter({
      limit: 5,
      windowMs: 60_000,
      now: () => 1_000,
      maxTrackedKeys: 64,
    });

    for (let index = 0; index < 32; index += 1) {
      expect(
        limiter.retryAfterMs([
          `email:person-${index}@example.com`,
          `ip:192.0.2.${index}`,
        ]),
      ).toBe(0);
    }
    expect(
      limiter.retryAfterMs([
        "email:capacity@example.com",
        "ip:198.51.100.1",
      ]),
    ).toBeGreaterThan(0);

    const attempts = (
      limiter as unknown as { attempts: Map<string, number[]> }
    ).attempts;
    expect(attempts.size).toBe(64);
  });

  test("key churn never evicts an actively blocked recovery victim", () => {
    const limiter = new RecoveryAttemptLimiter({
      limit: 2,
      windowMs: 60_000,
      now: () => 1_000,
      maxTrackedKeys: 4,
    });
    const victimKeys = ["email:victim@example.com", "ip:192.0.2.1"];

    expect(limiter.retryAfterMs(victimKeys)).toBe(0);
    expect(limiter.retryAfterMs(victimKeys)).toBe(0);
    expect(
      limiter.retryAfterMs(["email:filler@example.com", "ip:192.0.2.2"]),
    ).toBe(0);
    expect(
      limiter.retryAfterMs(["email:churn@example.com", "ip:192.0.2.3"]),
    ).toBeGreaterThan(0);
    expect(limiter.retryAfterMs(victimKeys)).toBeGreaterThan(0);
  });

  test("rate limiting globally removes expired one-off keys", () => {
    let now = 1_000;
    const limiter = new RecoveryAttemptLimiter({
      limit: 5,
      windowMs: 1_000,
      now: () => now,
    });

    for (let index = 0; index < 100; index += 1) {
      limiter.retryAfterMs([
        `email:person-${index}@example.com`,
        `ip:198.51.100.${index}`,
      ]);
    }
    now = 2_001;
    limiter.retryAfterMs(["email:current@example.com", "ip:203.0.113.1"]);

    const attempts = (
      limiter as unknown as { attempts: Map<string, number[]> }
    ).attempts;
    expect(attempts.size).toBe(2);
  });

  test("account-dependent provider rejection matches the accepted response", async () => {
    const request = () =>
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
        },
        body: JSON.stringify({
          email: "person@example.com",
          captcha_token: "captcha-proof",
        }),
      });
    const dependencies = (
      sendRecovery: (
        email: string,
        redirectTo: string,
        captchaToken: string,
      ) => Promise<void>,
    ) => ({
      configuredAppOrigin: "https://app.argus.example",
      environment: "production",
      limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
      globalLimiter: new RecoveryAttemptLimiter({
        limit: 100,
        windowMs: 60_000,
      }),
      sendRecovery,
    });

    const accepted = await handleRecoveryRequest(
      request(),
      dependencies(async () => undefined),
    );
    const rejected = await handleRecoveryRequest(
      request(),
      dependencies(async () => {
        throw new Error("account missing");
      }),
    );

    expect(accepted.status).toBe(202);
    expect(await accepted.json()).toEqual({ accepted: true });
    expect(rejected.status).toBe(accepted.status);
    expect(await rejected.json()).toEqual({ accepted: true });
  });

  test("classified CAPTCHA rejection is surfaced without provider detail", async () => {
    const response = await handleRecoveryRequest(
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
        },
        body: JSON.stringify({
          email: "person@example.com",
          captcha_token: "captcha-proof",
        }),
      }),
      {
        configuredAppOrigin: "https://app.argus.example",
        environment: "production",
        limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
        globalLimiter: new RecoveryAttemptLimiter({
          limit: 100,
          windowMs: 60_000,
        }),
        async sendRecovery() {
          throw new RecoveryCaptchaRejectedError();
        },
      },
    );

    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({ accepted: false });
  });

  test("recovery forwards one bounded CAPTCHA token to the provider", async () => {
    let providerToken = "";
    const response = await handleRecoveryRequest(
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
        },
        body: JSON.stringify({
          email: "person@example.com",
          captcha_token: "captcha-proof",
        }),
      }),
      {
        configuredAppOrigin: "https://app.argus.example",
        environment: "production",
        limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
        globalLimiter: new RecoveryAttemptLimiter({
          limit: 100,
          windowMs: 60_000,
        }),
        async sendRecovery(_email, _redirectTo, captchaToken) {
          providerToken = captchaToken;
        },
      },
    );
    const routeSource = readFileSync(
      join(import.meta.dir, "../app/api/auth/recovery/route.ts"),
      "utf-8",
    );

    expect(response.status).toBe(202);
    expect(providerToken).toBe("captcha-proof");
    expect(routeSource).toContain("captchaToken");
    expect(routeSource).toContain("captchaToken,");
  });

  test("recovery rejects missing or invalid CAPTCHA tokens before provider work", async () => {
    const captchaValues: unknown[] = [undefined, null, 42, "", "   ", "x".repeat(4_097)];

    for (const captchaToken of captchaValues) {
      let providerCalls = 0;
      const body: Record<string, unknown> = { email: "person@example.com" };
      if (captchaToken !== undefined) body.captcha_token = captchaToken;
      const response = await handleRecoveryRequest(
        new Request("https://app.argus.example/api/auth/recovery", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Origin: "https://app.argus.example",
          },
          body: JSON.stringify(body),
        }),
        {
          configuredAppOrigin: "https://app.argus.example",
          environment: "production",
          limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
          globalLimiter: new RecoveryAttemptLimiter({
            limit: 100,
            windowMs: 60_000,
          }),
          async sendRecovery() {
            providerCalls += 1;
          },
        },
      );

      expect(response.status).toBe(400);
      expect(providerCalls).toBe(0);
    }
  });

  test("recovery ignores a body-supplied redirect", async () => {
    let destination = "";
    const response = await handleRecoveryRequest(
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
        },
        body: JSON.stringify({
          email: "person@example.com",
          captcha_token: "captcha-proof",
          redirectTo: "https://attacker.example/steal",
        }),
      }),
      {
        configuredAppOrigin: "https://app.argus.example",
        environment: "production",
        limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
        globalLimiter: new RecoveryAttemptLimiter({
          limit: 100,
          windowMs: 60_000,
        }),
        async sendRecovery(_email, redirectTo) {
          destination = redirectTo;
        },
      },
    );

    expect(response.status).toBe(202);
    expect(destination).toBe("https://app.argus.example/auth/recovery");
  });

  test("recovery rejects null and malformed origins before provider work", async () => {
    for (const origin of ["null", "not-an-origin"]) {
      let providerCalls = 0;
      const response = await handleRecoveryRequest(
        new Request("https://app.argus.example/api/auth/recovery", {
          method: "POST",
          headers: { "Content-Type": "application/json", Origin: origin },
          body: JSON.stringify({ email: "person@example.com" }),
        }),
        {
          configuredAppOrigin: "https://app.argus.example",
          environment: "production",
          limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
          globalLimiter: new RecoveryAttemptLimiter({ limit: 100, windowMs: 60_000 }),
          async sendRecovery() {
            providerCalls += 1;
          },
        },
      );

      expect(response.status).toBe(403);
      expect(providerCalls).toBe(0);
    }
  });

  test("recovery rejects non-json and oversized bodies before provider work", async () => {
    const cases: Array<{ request: Request; status: number }> = [
      {
        request: new Request("https://app.argus.example/api/auth/recovery", {
          method: "POST",
          headers: {
            "Content-Type": "text/plain",
            Origin: "https://app.argus.example",
          },
          body: JSON.stringify({ email: "person@example.com" }),
        }),
        status: 415,
      },
      {
        request: new Request("https://app.argus.example/api/auth/recovery", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Origin: "https://app.argus.example",
          },
          body: JSON.stringify({ padding: "x".repeat(9_000) }),
        }),
        status: 413,
      },
    ];
    for (const { request, status } of cases) {
      let providerCalls = 0;
      const response = await handleRecoveryRequest(request, {
        configuredAppOrigin: "https://app.argus.example",
        environment: "production",
        limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
        globalLimiter: new RecoveryAttemptLimiter({ limit: 100, windowMs: 60_000 }),
        async sendRecovery() {
          providerCalls += 1;
        },
      });

      expect(response.status).toBe(status);
      expect(providerCalls).toBe(0);
    }
  });

  test("recovery rejects non-object JSON before provider work", async () => {
    let providerCalls = 0;
    const response = await handleRecoveryRequest(
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
        },
        body: "null",
      }),
      {
        configuredAppOrigin: "https://app.argus.example",
        environment: "production",
        limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
        globalLimiter: new RecoveryAttemptLimiter({ limit: 100, windowMs: 60_000 }),
        async sendRecovery() {
          providerCalls += 1;
        },
      },
    );

    expect(response.status).toBe(400);
    expect(providerCalls).toBe(0);
  });

  test("recovery bounds email and client-address inputs before provider work", async () => {
    const cases: Array<{ request: Request; status: number }> = [
      {
        request: new Request("https://app.argus.example/api/auth/recovery", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Origin: "https://app.argus.example",
          },
          body: JSON.stringify({ email: `${"x".repeat(243)}@example.com` }),
        }),
        status: 202,
      },
      {
        request: new Request("https://app.argus.example/api/auth/recovery", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Origin: "https://app.argus.example",
            "CF-Connecting-IP": "not-an-ip-address",
          },
          body: JSON.stringify({ email: "person@example.com" }),
        }),
        status: 400,
      },
    ];
    for (const { request, status } of cases) {
      let providerCalls = 0;
      const response = await handleRecoveryRequest(request, {
        configuredAppOrigin: "https://app.argus.example",
        environment: "production",
        limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
        globalLimiter: new RecoveryAttemptLimiter({ limit: 100, windowMs: 60_000 }),
        async sendRecovery() {
          providerCalls += 1;
        },
      });

      expect(response.status).toBe(status);
      expect(providerCalls).toBe(0);
    }
  });

  test("recovery global abuse budget fails closed with retry guidance", async () => {
    let providerCalls = 0;
    const globalLimiter = new RecoveryAttemptLimiter({
      limit: 1,
      windowMs: 60_000,
      now: () => 1_000,
    });
    const dependencies = {
      configuredAppOrigin: "https://app.argus.example",
      environment: "production",
      limiter: new RecoveryAttemptLimiter({
        limit: 5,
        windowMs: 60_000,
        now: () => 1_000,
      }),
      globalLimiter,
      async sendRecovery() {
        providerCalls += 1;
      },
    };
    const request = (email: string) =>
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
        },
        body: JSON.stringify({ email, captcha_token: "captcha-proof" }),
      });

    expect((await handleRecoveryRequest(request("one@example.com"), dependencies)).status).toBe(202);
    const blocked = await handleRecoveryRequest(
      request("two@example.com"),
      dependencies,
    );

    expect(blocked.status).toBe(429);
    expect(blocked.headers.get("Retry-After")).toBe("60");
    expect(await blocked.json()).toEqual({ accepted: false });
    expect(providerCalls).toBe(1);
  });

  test("invalid recovery emails do not consume the provider-wide budget", async () => {
    let providerCalls = 0;
    const dependencies = {
      configuredAppOrigin: "https://app.argus.example",
      environment: "production",
      limiter: new RecoveryAttemptLimiter({ limit: 5, windowMs: 60_000 }),
      globalLimiter: new RecoveryAttemptLimiter({ limit: 1, windowMs: 60_000 }),
      async sendRecovery() {
        providerCalls += 1;
      },
    };
    const request = (email: string, address: string) =>
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
          "CF-Connecting-IP": address,
        },
        body: JSON.stringify({
          email,
          ...(email.includes("@") ? { captcha_token: "captcha-proof" } : {}),
        }),
      });

    expect(
      (await handleRecoveryRequest(request("not-an-email", "192.0.2.10"), dependencies))
        .status,
    ).toBe(202);
    expect(
      (await handleRecoveryRequest(request("valid@example.com", "192.0.2.11"), dependencies))
        .status,
    ).toBe(202);
    expect(providerCalls).toBe(1);
  });

  test("locally blocked recovery attempts do not consume the provider-wide budget", async () => {
    let providerCalls = 0;
    const dependencies = {
      configuredAppOrigin: "https://app.argus.example",
      environment: "production",
      limiter: new RecoveryAttemptLimiter({ limit: 1, windowMs: 60_000 }),
      globalLimiter: new RecoveryAttemptLimiter({ limit: 2, windowMs: 60_000 }),
      async sendRecovery() {
        providerCalls += 1;
      },
    };
    const request = (email: string, address: string) =>
      new Request("https://app.argus.example/api/auth/recovery", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://app.argus.example",
          "CF-Connecting-IP": address,
        },
        body: JSON.stringify({ email, captcha_token: "captcha-proof" }),
      });

    expect(
      (await handleRecoveryRequest(request("one@example.com", "192.0.2.20"), dependencies))
        .status,
    ).toBe(202);
    expect(
      (await handleRecoveryRequest(request("one@example.com", "192.0.2.20"), dependencies))
        .status,
    ).toBe(429);
    expect(
      (await handleRecoveryRequest(request("two@example.com", "192.0.2.21"), dependencies))
        .status,
    ).toBe(202);
    expect(providerCalls).toBe(2);
  });

  test("account security confirmation labels are localized in English and Spanish", () => {
    const en = JSON.parse(
      readFileSync(join(import.meta.dir, "../public/locales/en/common.json"), "utf-8"),
    );
    const es = JSON.parse(
      readFileSync(join(import.meta.dir, "../public/locales/es-419/common.json"), "utf-8"),
    );

    expect(en.common.confirm).toBe("Confirm");
    expect(es.common.confirm).toBe("Confirmar");
  });
});
