"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, CheckCircle2, EyeClosed, Link2Off, LoaderCircle } from "lucide-react";
import { RecoveryShell } from "./RecoveryShell";
import styles from "./recovery.module.css";
import { useTranslation } from "react-i18next";

import { PasswordField, useFieldChecks } from "@/components/ui/FormField";
import {
  getAuthSecurityActions,
  type SessionActionResult,
} from "@/lib/auth-security";
import { inlineFailureTextClass } from "@/lib/failure-treatment";
import { PASSWORD_MIN_LENGTH } from "@/lib/password-strength";

type RecoveryState = "checking" | "ready" | "invalid" | "saving" | "done";

export function RecoveryReset({ actions = getAuthSecurityActions }: { actions?: typeof getAuthSecurityActions }) {
  const { t } = useTranslation();
  const exchangeStarted = useRef(false);
  const saving = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const [state, setState] = useState<RecoveryState>("checking");
  const [password, setPassword] = useState("");
  const [result, setResult] = useState<SessionActionResult | null>(null);
  const [retryingRevocation, setRetryingRevocation] = useState(false);
  const [error, setError] = useState<"auth.recovery.password_rejected" | "auth.recovery.revocation_retry_error" | null>(null);

  useEffect(() => {
    if (exchangeStarted.current) return;
    exchangeStarted.current = true;
    const code = new URLSearchParams(window.location.search).get("code");
    if (code) window.history.replaceState(null, "", window.location.pathname);
    if (!code) {
      Promise.resolve().then(() => actions().hasRecoverySession())
        .then((ready) => setState(ready ? "ready" : "invalid"))
        .catch(() => setState("invalid"));
      return;
    }
    try {
      actions()
        .exchangeRecoveryCode(code)
        .then(() => {
          setState("ready");
        })
        .catch(() => setState("invalid"));
    } catch {
      setState("invalid");
    }
  }, [actions]);

  useEffect(() => {
    if (state === "done" || state === "invalid") heading.current?.focus({ preventScroll: true });
  }, [state]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (state !== "ready" || saving.current) return;
    if (!checks.submit()) { document.getElementById("recovery-password")?.focus(); return; }
    saving.current = true;
    setState("saving");
    try {
      const resetResult = await actions().resetRecoveredPassword(
        password,
      );
      setPassword("");
      setResult(resetResult);
      setState("done");
    } catch {
      setError("auth.recovery.password_rejected");
      setState("ready");
    } finally { saving.current = false; }
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
  const revocationAuthorityMissing = result?.revocation === "failed" && result.revocationAuthority === "absent";

  const retryRevocation = async () => {
    setError(null);
    setRetryingRevocation(true);
    try {
      setResult(await actions().signOutAllSessions());
    } catch {
      setError("auth.recovery.revocation_retry_error");
    } finally {
      setRetryingRevocation(false);
    }
  };

  return (
    <RecoveryShell>
      {state !== "done" && <Link href="/?auth=login" className={styles.secondary}><ArrowLeft aria-hidden="true" size={16} />{t("auth.recovery.back_to_sign_in")}</Link>}
      {state === "invalid" && <Link2Off aria-hidden="true" className={styles.statusIcon} />}
      {state === "done" && <CheckCircle2 aria-hidden="true" className={styles.statusIcon} />}
        <h1 ref={heading} tabIndex={-1} className={`font-display ${styles.title}`}>
          {state === "done" ? t("auth.recovery.success_title") : state === "invalid" ? t("auth.recovery.link_title") : t("auth.recovery.reset_title")}
        </h1>

        {state === "checking" && (
          <p role="status" className="mt-4 text-sm text-[var(--auth-muted)]">
            {t("auth.recovery.checking", "Checking your recovery link...")}
          </p>
        )}

        {state === "invalid" && (
          <div className="mt-5 space-y-4">
            <p role="alert" className={`text-sm leading-relaxed ${inlineFailureTextClass}`}>
              {t(
                  "auth.recovery.invalid_link",
                  "This recovery link is missing, expired, or already used.",
                )}
            </p>
            <Link
              href="/auth/forgot-password"
              className={`${styles.primary} auth-primary`}
            >
              {t("auth.recovery.request_new", "Request a new link")}
            </Link>
          </div>
        )}

        {(state === "ready" || state === "saving") && (
          <form noValidate onSubmit={submit} aria-busy={state === "saving"} className={styles.form}>
            <PasswordField
              id="recovery-password"
              label={passwordLabel}
              autoComplete="new-password"
              placeholder={t("auth.form.password_hint")}
              coaching="on-focus"
              advice={t("auth.form.password_advice")}
              hideIcon={<EyeClosed className="h-5 w-5" aria-hidden="true" />}
              reserveMessages={[t("account_security.password.new_required"), t("account_security.password.too_short", { min: PASSWORD_MIN_LENGTH })]}
              value={password}
              error={checks.errorOf("password")}
              readOnly={state === "saving"}
              onBlur={() => checks.blur("password")}
              required
              onChange={(event) => { setPassword(event.target.value); setError(null); }}
            />
            <button
              type="submit"
              disabled={state === "saving"}
              aria-busy={state === "saving"}
              className={`${styles.primary} auth-primary`}
            >
              {state === "saving" && <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin motion-reduce:animate-none" />}
              {state === "saving"
                ? t("auth.recovery.updating", "Updating...")
                : t("auth.recovery.update_password", "Update password")}
            </button>
            {error && <p role="alert" className={`mt-3 text-sm ${inlineFailureTextClass}`}>{t(error)}</p>}
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
                {revocationAuthorityMissing
                  ? t("auth.recovery.revocation_authority_missing")
                  : t(
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
            {error && <p role="alert" className={`text-sm ${inlineFailureTextClass}`}>{t(error)}</p>}
            {result.revocation === "failed" && !revocationAuthorityMissing ? (
              <button
                type="button"
                disabled={retryingRevocation}
                onClick={() => void retryRevocation()}
                aria-busy={retryingRevocation}
                className={`${styles.primary} auth-primary`}
              >
                {retryingRevocation
                  ? t("auth.recovery.retrying_revocation", "Retrying...")
                  : t("auth.recovery.retry_revocation", "Retry sign out all sessions")}
              </button>
            ) : (
              <Link
                href="/?auth=login"
                className={`${styles.primary} auth-primary`}
              >
                {t("auth.recovery.back_to_sign_in", "Back to sign in")}
              </Link>
            )}
          </div>
        )}
    </RecoveryShell>
  );
}
