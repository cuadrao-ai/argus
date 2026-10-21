"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useTranslation } from "react-i18next";

import {
  getAuthSecurityActions,
  type SessionActionResult,
} from "@/lib/auth-security";
import { inlineFailureTextClass } from "@/lib/failure-treatment";

type RecoveryState = "checking" | "ready" | "invalid" | "saving" | "done";

export default function RecoveryPage() {
  const { t } = useTranslation();
  const exchangeStarted = useRef(false);
  const [state, setState] = useState<RecoveryState>("checking");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [result, setResult] = useState<SessionActionResult | null>(null);
  const [retryingRevocation, setRetryingRevocation] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (exchangeStarted.current) return;
    exchangeStarted.current = true;
    const code = new URLSearchParams(window.location.search).get("code");
    window.history.replaceState(null, "", "/auth/recovery");
    if (!code) {
      getAuthSecurityActions()
        .hasRecoverySession()
        .then((ready) => setState(ready ? "ready" : "invalid"))
        .catch(() => setState("invalid"));
      return;
    }
    try {
      getAuthSecurityActions()
        .exchangeRecoveryCode(code)
        .then(() => {
          setState("ready");
        })
        .catch(() => setState("invalid"));
    } catch {
      setState("invalid");
    }
  }, []);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (password !== confirmation) {
      setError(t("auth.recovery.password_mismatch", "Passwords do not match."));
      return;
    }
    setState("saving");
    try {
      const resetResult = await getAuthSecurityActions().resetRecoveredPassword(
        password,
      );
      setResult(resetResult);
      setState("done");
    } catch {
      setError(
        t(
          "auth.recovery.password_rejected",
          "We couldn’t update the password. Check the requirements or request a new recovery link.",
        ),
      );
      setState("ready");
    }
  };

  const retryRevocation = async () => {
    setError(null);
    setRetryingRevocation(true);
    try {
      setResult(await getAuthSecurityActions().signOutAllSessions());
    } catch {
      setError(
        t(
          "auth.recovery.revocation_retry_error",
          "Cuadrao still couldn’t confirm that every session was signed out. Try again.",
        ),
      );
    } finally {
      setRetryingRevocation(false);
    }
  };

  return (
    <main className="flex min-h-[100dvh] items-center justify-center px-6 py-12">
      <section className="w-full max-w-md rounded-[24px] border border-black/10 bg-white p-7 dark:border-white/10 dark:bg-[#151719]">
        <h1 className="font-display text-3xl font-medium tracking-tight text-black dark:text-white">
          {t("auth.recovery.reset_title", "Choose a new password")}
        </h1>

        {state === "checking" && (
          <p role="status" className="mt-4 text-sm text-black/55 dark:text-white/55">
            {t("auth.recovery.checking", "Checking your recovery link...")}
          </p>
        )}

        {state === "invalid" && (
          <div className="mt-5 space-y-4">
            <p role="alert" className={`text-sm leading-relaxed ${inlineFailureTextClass}`}>
              {error ??
                t(
                  "auth.recovery.invalid_link",
                  "This recovery link is missing, expired, or already used.",
                )}
            </p>
            <Link
              href="/auth/forgot-password"
              className="inline-flex rounded-full bg-black px-5 py-3 text-sm font-medium text-white dark:bg-white dark:text-black"
            >
              {t("auth.recovery.request_new", "Request a new link")}
            </Link>
          </div>
        )}

        {(state === "ready" || state === "saving") && (
          <form onSubmit={submit} className="mt-6 space-y-4">
            <label className="block text-sm font-medium text-black dark:text-white">
              {t("auth.recovery.new_password", "New password")}
              <input
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-2 w-full rounded-[18px] border border-black/15 bg-transparent px-4 py-3 text-base outline-none focus-visible:ring-2 focus-visible:ring-black dark:border-white/20 dark:focus-visible:ring-white"
              />
            </label>
            <label className="block text-sm font-medium text-black dark:text-white">
              {t("auth.recovery.confirm_password", "Confirm new password")}
              <input
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                className="mt-2 w-full rounded-[18px] border border-black/15 bg-transparent px-4 py-3 text-base outline-none focus-visible:ring-2 focus-visible:ring-black dark:border-white/20 dark:focus-visible:ring-white"
              />
            </label>
            {error && <p role="alert" className={`text-sm ${inlineFailureTextClass}`}>{error}</p>}
            <button
              type="submit"
              disabled={state === "saving"}
              className="w-full rounded-full bg-black px-5 py-3 font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
            >
              {state === "saving"
                ? t("auth.recovery.updating", "Updating...")
                : t("auth.recovery.update_password", "Update password")}
            </button>
          </form>
        )}

        {state === "done" && result && (
          <div className="mt-5 space-y-4">
            <p role="status" className="text-sm leading-relaxed text-emerald-700 dark:text-emerald-200">
              {result.revocation === "failed"
                ? t(
                    "auth.recovery.password_updated",
                    "Your password is updated.",
                  )
                : t(
                    "auth.recovery.reset_complete",
                    "Your password is updated. Sign in again on every browser.",
                  )}
            </p>
            {result.revocation === "failed" && (
              <p role="alert" className="text-sm leading-relaxed text-amber-700 dark:text-amber-200">
                {t(
                  "auth.recovery.revocation_warning",
                  "Cuadrao could not confirm that every session was signed out. Retry before signing in again.",
                )}
              </p>
            )}
            {result.revocation === "complete" && result.cookieSync === "failed" && (
              <p role="alert" className="text-sm leading-relaxed text-amber-700 dark:text-amber-200">
                {t(
                  "auth.recovery.cleanup_warning",
                  "Sessions were revoked, but this browser could not confirm local cookie cleanup. A fresh sign-in is still required.",
                )}
              </p>
            )}
            {error && <p role="alert" className={`text-sm ${inlineFailureTextClass}`}>{error}</p>}
            {result.revocation === "failed" ? (
              <button
                type="button"
                disabled={retryingRevocation}
                onClick={() => void retryRevocation()}
                className="inline-flex rounded-full bg-black px-5 py-3 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
              >
                {retryingRevocation
                  ? t("auth.recovery.retrying_revocation", "Retrying...")
                  : t("auth.recovery.retry_revocation", "Retry sign out all sessions")}
              </button>
            ) : (
              <Link
                href="/?auth=login"
                className="inline-flex rounded-full bg-black px-5 py-3 text-sm font-medium text-white dark:bg-white dark:text-black"
              >
                {t("auth.recovery.back_to_sign_in", "Back to sign in")}
              </Link>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
