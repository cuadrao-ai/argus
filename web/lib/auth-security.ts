import { clearArgusSessionCookies } from "./argus-api";
import { classifyFailure, emailRetrySeconds } from "./failure-screen";
import { acquirePasswordAuthCaptchaToken } from "./guest-captcha";
import { PASSWORD_MIN_LENGTH } from "./password-strength";
import { getSupabaseClient } from "./supabase-client";

export type AuthSecurityPort = {
  exchangeCodeForSession: (
    code: string,
  ) => Promise<{ error: unknown | null }>;
  updateUser: (
    attributes: Record<string, string>,
  ) => Promise<{ error: unknown | null }>;
  signOut: (options: {
    scope: "local" | "others" | "global";
  }) => Promise<{ error: unknown | null }>;
  hasSession?: () => Promise<boolean>;
};

export type SessionActionResult = {
  currentSessionPreserved: boolean | "unknown";
  freshLoginRequired: boolean;
  revocation: "complete" | "failed";
  cookieSync: "not_required" | "cleared" | "failed";
};

type ClearArgusCookies = () => Promise<void>;

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
) {
  const signOut = async (
    scope: "local" | "others" | "global",
  ): Promise<SessionActionResult> => {
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
    let cookieSync: SessionActionResult["cookieSync"] = "cleared";
    try {
      await clearCookies();
    } catch {
      cookieSync = "failed";
    }
    return {
      currentSessionPreserved: revocationError ? "unknown" : false,
      freshLoginRequired: revocationError === null,
      revocation: revocationError ? "failed" : "complete",
      cookieSync,
    };
  };

  return {
    async exchangeRecoveryCode(code: string): Promise<void> {
      if (!code) throw new Error("Missing recovery code.");
      const { error } = await auth.exchangeCodeForSession(code);
      throwOnAuthError(error);
    },

    async hasRecoverySession(): Promise<boolean> {
      if (!auth.hasSession) return false;
      try {
        return await auth.hasSession();
      } catch {
        return false;
      }
    },

    async resetRecoveredPassword(
      newPassword: string,
    ): Promise<SessionActionResult> {
      if (newPassword.length < PASSWORD_MIN_LENGTH) throw new Error("Password is too short.");
      const { error } = await auth.updateUser({ password: newPassword });
      throwOnAuthError(error);
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
  };
}

export function getAuthSecurityActions() {
  const supabase = getSupabaseClient();
  if (!supabase) {
    throw new Error("Authentication is not configured.");
  }
  const auth: AuthSecurityPort = {
    exchangeCodeForSession: (code) => supabase.auth.exchangeCodeForSession(code),
    updateUser: (attributes) => supabase.auth.updateUser(attributes),
    signOut: (options) => supabase.auth.signOut(options),
    hasSession: async () => {
      const { data, error } = await supabase.auth.getUser();
      return error === null && data.user !== null;
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
