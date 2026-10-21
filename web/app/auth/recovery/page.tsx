"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useTranslation } from "react-i18next";

import { ErrorSummary, PasswordField, useFieldChecks } from "@/components/ui/FormField";
import {
  getAuthSecurityActions,
  type SessionActionResult,
} from "@/lib/auth-security";
import { inlineFailureTextClass } from "@/lib/failure-treatment";
import { PASSWORD_MIN_LENGTH } from "@/lib/password-strength";

type RecoveryState = "checking" | "ready" | "invalid" | "saving" | "done";

export default function RecoveryPage() {
  const { t } = useTranslation();
  const exchangeStarted = useRef(false);
  const [state, setState] = useState<RecoveryState>("checking");
  const [password, setPassword] = useState("");
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
    if (!checks.submit()) return;
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

  const checks = useFieldChecks(
    {
      password: (values) =>
        !values.password
          ? t("account_security.password.new_required", "Enter a new password.")
          : values.password.length < PASSWORD_MIN_LENGTH
            ? t("account_security.password.too_short", { min: PASSWORD_MIN_LENGTH, defaultValue: "Use at least {{min}} characters." })
            : null,
    },
    { password },
  );
  const passwordLabel = t("auth.recovery.new_password", "New password");

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
    <main data-auth-brand="cuadrao" className="flex min-h-[100dvh] items-center justify-center bg-[var(--auth-paper)] px-6 py-12">
      <section className="w-full max-w-md rounded-[20px] border border-[var(--auth-line)] bg-[var(--auth-paper)] p-7">
        <h1 className="font-display text-3xl font-medium tracking-tight text-[var(--auth-ink)]">
          {t("auth.recovery.reset_title", "Choose a new password")}
        </h1>

        {state === "checking" && (
          <p role="status" className="mt-4 text-sm text-[var(--auth-muted)]">
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
              className="inline-flex rounded-full auth-primary bg-[var(--auth-pine)] text-[var(--auth-on-pine)] hover:bg-[var(--auth-pine-hover)] min-h-11 px-5 py-3 text-sm font-medium"
            >
              {t("auth.recovery.request_new", "Request a new link")}
            </Link>
          </div>
        )}

        {(state === "ready" || state === "saving") && (
          <form noValidate onSubmit={submit} className="mt-6 space-y-4">
            <ErrorSummary
              key={checks.attempt}
              title={t("common.form_summary", "Check these fields to continue:")}
              items={checks.summary.map(() => ({ id: "recovery-password", label: passwordLabel }))}
            />
            <PasswordField
              id="recovery-password"
              label={passwordLabel}
              autoComplete="new-password"
              value={password}
              error={checks.errorOf("password")}
              disabled={state === "saving"}
              onBlur={() => checks.blur("password")}
              onChange={(event) => setPassword(event.target.value)}
            />
            {error && <p role="alert" className={`text-sm ${inlineFailureTextClass}`}>{error}</p>}
            <button
              type="submit"
              disabled={state === "saving"}
              className="w-full rounded-full auth-primary bg-[var(--auth-pine)] text-[var(--auth-on-pine)] hover:bg-[var(--auth-pine-hover)] min-h-11 px-5 py-3 font-display font-medium disabled:opacity-50"
            >
              {state === "saving"
                ? t("auth.recovery.updating", "Updating...")
                : t("auth.recovery.update_password", "Update password")}
            </button>
          </form>
        )}

        {state === "done" && result && (
          <div className="mt-5 space-y-4">
            <p role="status" className="text-sm leading-relaxed text-[var(--auth-pine)]">
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
                className="inline-flex rounded-full auth-primary bg-[var(--auth-pine)] text-[var(--auth-on-pine)] hover:bg-[var(--auth-pine-hover)] min-h-11 px-5 py-3 text-sm font-medium disabled:opacity-50"
              >
                {retryingRevocation
                  ? t("auth.recovery.retrying_revocation", "Retrying...")
                  : t("auth.recovery.retry_revocation", "Retry sign out all sessions")}
              </button>
            ) : (
              <Link
                href="/?auth=login"
                className="inline-flex rounded-full auth-primary bg-[var(--auth-pine)] text-[var(--auth-on-pine)] hover:bg-[var(--auth-pine-hover)] min-h-11 px-5 py-3 text-sm font-medium"
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
