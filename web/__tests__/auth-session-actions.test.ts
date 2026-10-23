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

  test("cookie cleanup retries return cleanup status without repeating provider actions", async () => {
    const port = authPort();
    let cookieClears = 0;
    const actions = createAuthSecurityActions(port.auth, async () => {
      cookieClears += 1;
      if (cookieClears < 3) throw new Error("cookie cleanup unavailable");
    });
    const result = await actions.changePassword({ currentPassword: "old-password", newPassword: "new-password" });
    port.auth.getValidatedSession = async () => { throw new Error("ended session must not be checked"); };

    expect(result.revocation).toBe("complete");
    expect(result.freshLoginRequired).toBe(true);
    expect(result.cookieSync).toBe("failed");
    expect(await actions.retryCookieCleanup()).toBe("failed");
    expect(await actions.retryCookieCleanup()).toBe("cleared");
    expect(cookieClears).toBe(3);
    expect(port.updates).toHaveLength(1);
    expect(port.scopes).toEqual(["global"]);
  });
});
