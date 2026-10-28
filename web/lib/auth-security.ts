import { clearArgusSessionCookies } from "./argus-api";
import { readSessionStored, removeSessionStored, writeSessionStored } from "./browser-storage";
import { classifyFailure, emailRetrySeconds } from "./failure-screen";
import { acquirePasswordAuthCaptchaToken } from "./guest-captcha";
import { PASSWORD_MIN_LENGTH } from "./password-strength";
import { recoveryProof } from "./recovery-proof";
import { getSupabaseClient } from "./supabase-client";

export type AuthSecurityPort = {
  exchangeCodeForSession: (
    code: string,
  ) => Promise<{ data?: { redirectType?: string | null } | null; error: unknown | null }>;
  getValidatedSession?: () => Promise<{ userId: string; sessionId: string } | null>;
  updateUser: (
    attributes: Record<string, string>,
  ) => Promise<{ error: unknown | null }>;
  signOut: (options: {
    scope: "local" | "others" | "global";
  }) => Promise<{ error: unknown | null }>;
};

export type SessionActionResult = {
  currentSessionPreserved: boolean | "unknown";
  freshLoginRequired: boolean;
  revocation: "complete" | "failed";
  cookieSync: "not_required" | "cleared" | "failed";
  revocationAuthority?: "absent" | "unknown" | "present";
};

type ClearArgusCookies = () => Promise<void>;
type RecoveryProofStore = Pick<Storage, "getItem" | "setItem" | "removeItem">;
const RECOVERY_PROOF_KEY = "cuadrao:recovery-session:v1";

type AuthIdentityReader = {
  getClaims: () => Promise<{ data: { claims: { sub?: string; session_id?: string } } | null; error: unknown | null }>;
  getUser: () => Promise<{ data: { user: { id: string } | null }; error: unknown | null }>;
};

function knownEndedSession(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const detail = error as { name?: unknown; code?: unknown; status?: unknown };
  return detail.name === "AuthSessionMissingError"
    || detail.status === 401
    || ["bad_jwt", "invalid_jwt", "session_not_found", "session_expired",
      "refresh_token_not_found", "refresh_token_already_used"].includes(String(detail.code));
}

export async function readValidatedAuthSession(auth: AuthIdentityReader): Promise<{ userId: string; sessionId: string } | null> {
  const claims = await auth.getClaims();
  if (claims.error) {
    if (knownEndedSession(claims.error)) return null;
    throw claims.error;
  }
  if (!claims.data?.claims) return null;
  const user = await auth.getUser();
  if (user.error) {
    if (knownEndedSession(user.error)) return null;
    throw user.error;
  }
  const userId = user.data.user?.id;
  const sessionId = claims.data.claims.session_id;
  if (!userId || !sessionId || claims.data.claims.sub !== userId) return null;
  return { userId, sessionId };
}

export function accountSecurityLoadFailureAction(
  error: unknown,
): "redirect_to_login" | "closed" | "server" | "retry" {
  const kind = classifyFailure(error);
  if (kind === "session_ended") return "redirect_to_login";
  if (kind === "closed" || kind === "removed") return "closed";
  if (kind === "unavailable" || kind === "server") return "server";
  return "retry";
}

export class RecoveryRequestError extends Error {
  readonly status: number;
  readonly retryAfterSeconds: number;

  constructor(status: number, retryAfterSeconds: number) {
    super("Recovery request failed.");
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

function throwOnAuthError(error: unknown | null): void {
  if (!error) return;
  throw error instanceof Error ? error : new Error("Authentication request failed.");
}

export function createAuthSecurityActions(
  auth: AuthSecurityPort,
  clearCookies: ClearArgusCookies,
  recoveryStore?: RecoveryProofStore,
) {
  const store: RecoveryProofStore = recoveryStore ?? {
    getItem: () => readSessionStored(RECOVERY_PROOF_KEY),
    setItem: (_key, value) => {
      if (!writeSessionStored(RECOVERY_PROOF_KEY, value)) throw new Error("Recovery session could not be saved.");
    },
    removeItem: () => removeSessionStored(RECOVERY_PROOF_KEY),
  };
  const clearRecoveryProof = () => {
    try { store?.removeItem(RECOVERY_PROOF_KEY); } catch { /* Storage may be unavailable. */ }
  };
  const currentRecoveryProof = async () => {
    if (!store || !auth.getValidatedSession) return null;
    const identity = await auth.getValidatedSession();
    if (!identity) return null;
    return recoveryProof(identity.userId, identity.sessionId);
  };
  const keepRecoveryProof = async (proof: string | null) => {
    if (!proof) throw new Error("Recovery session could not be verified.");
    if (!store) throw new Error("Recovery session could not be saved.");
    try { store.setItem(RECOVERY_PROOF_KEY, proof); }
    catch { throw new Error("Recovery session could not be saved."); }
  };
  const hasRecoveryProof = async () => {
    let stored: string | null;
    try {
      stored = store.getItem(RECOVERY_PROOF_KEY);
    } catch {
      return false;
    }
    if (!stored) return false;
    let current: string | null;
    try { current = await currentRecoveryProof(); }
    catch { return false; } // A provider outage must not discard a valid recovery proof.
    if (current && stored === current) return true;
    clearRecoveryProof();
    return false;
  };
  const retryCookieCleanup = async (): Promise<"cleared" | "failed"> => {
    try {
      await clearCookies();
      return "cleared";
    } catch {
      return "failed";
    }
  };
  const signOut = async (
    scope: "local" | "others" | "global",
  ): Promise<SessionActionResult> => {
    if (scope !== "local") {
      let identity: { userId: string; sessionId: string } | null = null;
      let authority: "absent" | "unknown" = "absent";
      try { identity = await auth.getValidatedSession?.() ?? null; }
      catch { authority = "unknown"; }
      if (!identity) {
        if (scope === "others") throw new Error("Session could not be verified.");
        return {
          currentSessionPreserved: "unknown",
          freshLoginRequired: false,
          revocation: "failed",
          cookieSync: "not_required",
          revocationAuthority: authority,
        };
      }
    }
    let revocationError: unknown | null = null;
    try {
      const { error } = await auth.signOut({ scope });
      revocationError = error;
    } catch (error) {
      revocationError = error;
    }
    if (scope === "others") {
      throwOnAuthError(revocationError);
      return {
        currentSessionPreserved: true,
        freshLoginRequired: false,
        revocation: "complete",
        cookieSync: "not_required",
      };
    }
    if (revocationError) {
      return {
        currentSessionPreserved: "unknown",
        freshLoginRequired: false,
        revocation: "failed",
        cookieSync: "not_required",
        revocationAuthority: "present",
      };
    }
    clearRecoveryProof();
    const cookieSync = await retryCookieCleanup();
    return {
      currentSessionPreserved: false,
      freshLoginRequired: true,
      revocation: "complete",
      cookieSync,
    };
  };

  return {
    async exchangeRecoveryCode(code: string): Promise<void> {
      if (!code) throw new Error("Missing recovery code.");
      clearRecoveryProof();
      const { data, error } = await auth.exchangeCodeForSession(code);
      throwOnAuthError(error);
      if (data?.redirectType !== "recovery") throw new Error("The link is not a recovery link.");
      await keepRecoveryProof(await currentRecoveryProof());
    },

    // The server confirm route verified the recovery link and set the session;
    // its proof counts only when it names this browser's live session.
    async acceptRecoveryProof(proof: string): Promise<void> {
      clearRecoveryProof();
      const current = await currentRecoveryProof();
      await keepRecoveryProof(current && current === proof ? current : null);
    },

    async hasRecoverySession(): Promise<boolean> {
      return hasRecoveryProof();
    },

    async resetRecoveredPassword(
      newPassword: string,
    ): Promise<SessionActionResult> {
      if (newPassword.length < PASSWORD_MIN_LENGTH) throw new Error("Password is too short.");
      if (!await hasRecoveryProof()) throw new Error("Recovery session is required.");
      const { error } = await auth.updateUser({ password: newPassword });
      throwOnAuthError(error);
      clearRecoveryProof();
      return signOut("global");
    },

    async changePassword({
      currentPassword,
      newPassword,
    }: {
      currentPassword: string;
      newPassword: string;
    }): Promise<SessionActionResult> {
      if (!currentPassword) throw new Error("Current password is required.");
      if (newPassword.length < PASSWORD_MIN_LENGTH) throw new Error("Password is too short.");
      // One native request: the provider verifies current_password under
      // security_update_password_require_current_password, and recovery
      // sessions are natively exempt. A rejected update leaves the current
      // session, cookies, and auth.sessions rows untouched.
      const { error } = await auth.updateUser({
        password: newPassword,
        current_password: currentPassword,
      });
      throwOnAuthError(error);
      return signOut("global");
    },

    signOutThisBrowser: () => signOut("local"),
    signOutOtherSessions: () => signOut("others"),
    signOutAllSessions: () => signOut("global"),
    retryCookieCleanup,
  };
}

export function getAuthSecurityActions() {
  const supabase = getSupabaseClient();
  if (!supabase) {
    throw new Error("Authentication is not configured.");
  }
  const auth: AuthSecurityPort = {
    exchangeCodeForSession: async (code) => {
      const result = await supabase.auth.exchangeCodeForSession(code);
      const data = result.data as typeof result.data & { redirectType?: string | null };
      return { data: { redirectType: data?.redirectType ?? null }, error: result.error };
    },
    updateUser: (attributes) => supabase.auth.updateUser(attributes),
    signOut: (options) => supabase.auth.signOut(options),
    getValidatedSession: async () => {
      return readValidatedAuthSession(supabase.auth);
    },
  };
  return createAuthSecurityActions(auth, async () => {
    await clearArgusSessionCookies();
  });
}

export async function requestPasswordRecovery(email: string): Promise<void> {
  const captchaToken = await acquirePasswordAuthCaptchaToken();
  const response = await fetch("/api/auth/recovery", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ email, captcha_token: captchaToken }),
  });
  if (!response.ok) {
    const retryAfter = response.status === 429
      ? emailRetrySeconds(response.headers.get("Retry-After"))
      : 0;
    throw new RecoveryRequestError(response.status, retryAfter);
  }
}
