"use client";

import {
  type FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import Link from "next/link";
import { AlertCircle, ChevronLeft, CircleCheck, EyeClosed, LoaderCircle } from "lucide-react";
import { signedInHomePath } from "@/lib/landing-intent";
import { useTranslation } from "react-i18next";

import {
  dangerButtonClass,
  primaryButtonClass,
  quietButtonClass,
} from "@/components/business-app/business-ui";
import styles from "./account-security.module.css";
import { BusinessClosedNotice } from "@/components/status/BusinessClosedNotice";
import { ServerErrorScreen } from "@/components/status/ServerErrorScreen";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { PasswordField, useFieldChecks, type FieldRules } from "@/components/ui/FormField";
import { fieldHintClass, fieldNoteTone } from "@/components/ui/form-field";
import {
  accountSecurityLoadFailureAction,
  getAuthSecurityActions,
  type SessionActionResult,
} from "@/lib/auth-security";
import { getMe } from "@/lib/argus-api";
import { PASSWORD_MIN_LENGTH } from "@/lib/password-strength";
import { referenceCode, runQuietRetries, sessionEndedLoginPath } from "@/lib/failure-screen";

type SignOutScope = "local" | "others" | "global";
type Confirmation = Exclude<SignOutScope, "local"> | null;
type Section = "password" | "sessions";
type Busy = "password" | "cookies" | SignOutScope | null;
type AuthCheckState = "checking" | "ready" | "unavailable" | "closed" | "server";
type RetryTarget = SignOutScope | "password" | { kind: "cookies"; successMessage: string };
/** What the last action left on screen, shown inside the section it came from. */
type Outcome =
  | { kind: "done"; section: Section; text: string }
  | { kind: "warning" | "error"; section: Section; text: string; retry: RetryTarget };


type PasswordFieldName = "current" | "next";
const PASSWORD_FIELDS: { name: PasswordFieldName; id: string; autoComplete: "current-password" | "new-password" }[] = [
  { name: "current", id: "current-password", autoComplete: "current-password" },
  { name: "next", id: "new-password", autoComplete: "new-password" },
];
const EMPTY_PASSWORDS: Record<PasswordFieldName, string> = { current: "", next: "" };

export function AccountSecurity({ actions = getAuthSecurityActions, loadSession = getMe }: {
  actions?: typeof getAuthSecurityActions;
  loadSession?: () => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const authChecked = useRef(false);
  const passwordPending = useRef(false);
  const passwordForm = useRef<HTMLFormElement>(null);
  const [authCheckState, setAuthCheckState] =
    useState<AuthCheckState>("checking");
  const [busy, setBusy] = useState<Busy>(null);
  const [confirmation, setConfirmation] = useState<Confirmation>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [passwords, setPasswords] = useState(EMPTY_PASSWORDS);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [freshLogin, setFreshLogin] = useState(false);
  const [reference, setReference] = useState("");

  const rules: FieldRules<PasswordFieldName> = {
    current: (values) =>
      values.current ? null : t("account_security.password.current_required", "Enter your current password."),
    next: (values) =>
      !values.next
        ? t("account_security.password.new_required", "Enter a new password.")
        : values.next.length < PASSWORD_MIN_LENGTH
          ? t("account_security.password.too_short", { min: PASSWORD_MIN_LENGTH, defaultValue: "Use at least {{min}} characters." })
          : null,
  };
  const checks = useFieldChecks(rules, passwords);
  useEffect(() => {
    if (checks.attempt > 0) passwordForm.current?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus();
  }, [checks.attempt]);

  const checkSession = useCallback(() => {
    setAuthCheckState("checking");
    runQuietRetries(() => loadSession())
      .then(() => setAuthCheckState("ready"))
      .catch((loadError: unknown) => {
        const action = accountSecurityLoadFailureAction(loadError);
        if (action === "redirect_to_login") {
          window.location.replace(sessionEndedLoginPath("/account/security", window.location.search));
          return;
        }
        if (action === "closed") {
          setAuthCheckState("closed");
          return;
        }
        if (action === "server") {
          setReference(referenceCode(loadError));
          setAuthCheckState("server");
          return;
        }
        setAuthCheckState("unavailable");
      });
  }, [loadSession]);

  useEffect(() => {
    if (authChecked.current) return;
    authChecked.current = true;
    checkSession();
  }, [checkSession]);

  const applyResult = (
    section: Section,
    retry: SignOutScope,
    result: SessionActionResult,
    successMessage: string,
    revocationWarning: string,
  ) => {
    if (result.revocation === "failed") {
      setOutcome({ kind: "warning", section, text: revocationWarning, retry });
    } else if (result.cookieSync === "failed") {
      setOutcome({
        kind: "warning",
        section,
        retry: { kind: "cookies", successMessage },
        text: t(
          "account_security.cookie_sync_warning",
          "Sessions were revoked, but local cookie cleanup could not be confirmed.",
        ),
      });
    } else {
      setOutcome({ kind: "done", section, text: successMessage });
    }
    setFreshLogin(result.freshLoginRequired);
  };

  const changePassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (passwordPending.current || busy !== null || freshLogin) return;
    setOutcome(null);
    if (!checks.submit()) return;
    passwordPending.current = true;
    setBusy("password");
    try {
      const result = await actions().changePassword({
        currentPassword: passwords.current,
        newPassword: passwords.next,
      });
      applyResult(
        "password",
        "global",
        result,
        t(
          "account_security.password.changed",
          "Password changed. Sign in again on every browser.",
        ),
        t(
          "account_security.password.revocation_warning",
          "Password changed, but Cuadrao could not confirm every session was signed out. Retry Sign out all sessions.",
        ),
      );
      setPasswords(EMPTY_PASSWORDS);
      checks.reset();
    } catch {
      setOutcome({
        kind: "error",
        section: "password",
        retry: "password",
        text: t(
          "account_security.password.error",
          "We couldn’t change the password. Check your current password and try again.",
        ),
      });
    } finally {
      passwordPending.current = false;
      setBusy(null);
    }
  };

  const signOut = async (scope: SignOutScope) => {
    const fromConfirmation = scope !== "local" && confirmation !== null;
    setConfirmError(null);
    setOutcome(null);
    setBusy(scope);
    try {
      const service = actions();
      const result =
        scope === "local"
          ? await service.signOutThisBrowser()
          : scope === "others"
            ? await service.signOutOtherSessions()
            : await service.signOutAllSessions();
      setConfirmation(null);
      applyResult(
        "sessions",
        scope,
        result,
        scope === "others"
          ? t(
              "account_security.sessions.others_complete",
              "Other sessions are signed out. This browser remains signed in.",
            )
          : t(
              "account_security.sessions.signed_out",
              "The selected sessions are signed out.",
            ),
        t(
          "account_security.sessions.revocation_warning",
          "Cuadrao could not confirm the selected sessions were signed out. Try the session action again.",
        ),
      );
    } catch {
      const text = t(
        "account_security.sessions.error",
        "We couldn’t complete that session change. Try again.",
      );
      if (fromConfirmation) setConfirmError(text);
      else setOutcome({ kind: "error", section: "sessions", text, retry: scope });
    } finally {
      setBusy(null);
    }
  };

  const retry = async (target: RetryTarget, section: Section) => {
    if (typeof target === "object") {
      if (busy !== null) return;
      setBusy("cookies");
      try {
        if (await actions().retryCookieCleanup() === "cleared") {
          setOutcome({ kind: "done", section, text: target.successMessage });
        }
      } finally {
        setBusy(null);
      }
    } else if (target === "password") passwordForm.current?.requestSubmit();
    else void signOut(target);
  };

  const retryLabel = t("account_security.retry", "Retry");
  const outcomeFor = (section: Section): ReactNode => {
    if (outcome?.section !== section) return null;
    if (outcome.kind === "done") {
      return (
        <div aria-busy={busy === "password"} className="mt-6 space-y-3">
          <p role="status" className="flex items-start gap-2 rounded-item bg-[#e3ebe1] px-4 py-3 text-[15px] leading-relaxed text-[#2f5a49] dark:bg-[#8fcbb0]/10 dark:text-[#8fcbb0]">
            <CircleCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            {outcome.text}
          </p>
          {freshLogin && (
            <Link href="/?auth=login" className={primaryButtonClass}>
              {t("auth.recovery.back_to_sign_in", "Back to sign in")}
            </Link>
          )}
        </div>
      );
    }
    const tone =
      outcome.kind === "warning"
        ? "bg-[#f2e8c9] text-[#735c14] dark:bg-[#f2e8c9]/10 dark:text-[#e6cf8a]"
        : "bg-[#f6dfe0] text-[#9e2f39] dark:bg-[#ec9aa0]/10 dark:text-[#ec9aa0]";
    return (
      <div role="alert" className={`mt-[21px] flex items-start gap-2 rounded-item px-4 py-3 text-[15px] leading-relaxed ${tone}`}>
        <AlertCircle className="mt-1 h-4 w-4 shrink-0" aria-hidden="true" />
        <div className="min-w-0">
          <p>{outcome.text}</p>
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => void retry(outcome.retry, section)}
            className={`${quietButtonClass} -ml-1`}
          >
            {retryLabel}
          </button>
        </div>
      </div>
    );
  };

  if (authCheckState === "closed") return <BusinessClosedNotice />;
  if (authCheckState === "server") {
    return <ServerErrorScreen reference={reference} onRetry={checkSession} />;
  }

  if (authCheckState !== "ready") {
    return (
      <main className="business-foundation flex min-h-[100dvh] items-center justify-center bg-[#F7F5EE] px-4 text-[16px] text-[#56635e] dark:bg-[#141517] dark:text-white/65">
        {authCheckState === "checking" ? (
          <p role="status">{t("account_security.loading", "Checking your session...")}</p>
        ) : (
          <div className="max-w-sm text-center">
            <p role="alert" className="text-[#172b26] dark:text-white">
              {t(
                "account_security.session_check_unavailable",
                "Cuadrao couldn’t verify your session right now. Try again.",
              )}
            </p>
            <button type="button" onClick={checkSession} className={`${primaryButtonClass} mt-[21px]`}>
              {retryLabel}
            </button>
          </div>
        )}
      </main>
    );
  }

  const disabled = busy !== null || freshLogin;
  const passwordLabels: Record<PasswordFieldName, string> = {
    current: t("account_security.password.current", "Current password"),
    next: t("account_security.password.new", "New password"),
  };
  const sessionChoices: {
    scope: SignOutScope;
    title: string;
    line: string;
    action: string;
    name: string;
    look: string;
    run: () => void;
  }[] = [
    {
      scope: "local",
      title: t("account_security.sessions.this_title", "This browser"),
      line: t("account_security.sessions.this_line", "Other sessions stay signed in."),
      action: t("account_security.sessions.this_action", "Sign out"),
      name: t("account_security.sessions.sign_out_this", "Sign out this browser"),
      look: quietButtonClass,
      run: () => void signOut("local"),
    },
    {
      scope: "others",
      title: t("account_security.sessions.others_title", "Other sessions"),
      line: t("account_security.sessions.others_line", "Keep this browser signed in."),
      action: t("account_security.sessions.others_action", "Sign out others"),
      name: t("account_security.sessions.sign_out_others", "Sign out other sessions"),
      look: quietButtonClass,
      run: () => setConfirmation("others"),
    },
    {
      scope: "global",
      title: t("account_security.sessions.all_title", "Everywhere"),
      line: t("account_security.sessions.all_line", "Includes this browser. Sign in again to continue."),
      action: t("account_security.sessions.all_action", "Sign out everywhere"),
      name: t("account_security.sessions.sign_out_all", "Sign out all sessions"),
      look: `${dangerButtonClass} ${fieldNoteTone.error}`,
      run: () => setConfirmation("global"),
    },
  ];

  return (
    <main data-auth-brand="cuadrao" className={`business-foundation ${styles.screen}`}>
      <div className={styles.column}>
        <Link href={signedInHomePath()} className={`${quietButtonClass} -ml-1`}>
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          {t("account_security.back", "Back to Cuadrao")}
        </Link>
        <h1 className="mt-[21px] font-display text-[26px] font-medium tracking-tight">
          {t("account_security.title", "Account security")}
        </h1>
        <p className="mt-2 text-[16px] leading-relaxed text-[#56635e] dark:text-white/65">
          {t(
            "account_security.description",
            "Change your password or choose exactly which sessions to sign out.",
          )}
        </p>

        <section aria-labelledby="password-title" className={`mt-[34px] ${styles.card}`}>
          <h2 id="password-title" className="font-display text-[21px] font-medium">
            {t("account_security.password.title", "Change password")}
          </h2>
          <p className={`mt-1 ${fieldHintClass}`}>
            {t(
              "account_security.password.description",
              "Enter your current password. After the change, every browser must sign in again.",
            )}
          </p>
          <form ref={passwordForm} noValidate onSubmit={changePassword} aria-busy={busy === "password"} className="mt-6 space-y-3">
            {PASSWORD_FIELDS.map((field) => (
              <PasswordField
                key={field.id}
                id={field.id}
                label={passwordLabels[field.name]}
                error={checks.errorOf(field.name)}
                autoComplete={field.autoComplete}
                placeholder={t("auth.form.password_hint")}
                coaching="on-focus"
                advice={t("auth.form.password_advice")}
                hideIcon={<EyeClosed className="h-5 w-5" aria-hidden="true" />}
                required
                reserveMessages={field.name === "current"
                  ? [t("account_security.password.current_required")]
                  : [t("account_security.password.new_required"), t("account_security.password.too_short", { min: PASSWORD_MIN_LENGTH })]}
                value={passwords[field.name]}
                readOnly={busy !== null}
                disabled={freshLogin}
                onBlur={() => checks.blur(field.name)}
                onChange={(event) => {
                  const value = event.target.value;
                  setPasswords((was) => ({ ...was, [field.name]: value }));
                  setOutcome(was => was?.section === "password" && was.kind === "error" ? null : was);
                }}
              />
            ))}
            {freshLogin ? null : (
              <div className="pt-2">
                <button type="submit" disabled={disabled} aria-busy={busy === "password"} className={`${primaryButtonClass} ${styles.submit}`}>
                  {busy === "password" && <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin motion-reduce:animate-none" />}
                  {busy === "password"
                    ? t("account_security.password.changing", "Changing...")
                    : t("account_security.password.submit", "Change password")}
                </button>
              </div>
            )}
          </form>
          {outcomeFor("password")}
        </section>

        <section aria-labelledby="sessions-title" className={`${styles.sessions} ${styles.card}`}>
          <h2 id="sessions-title" className="font-display text-[21px] font-medium">
            {t("account_security.sessions.title", "Sessions")}
          </h2>
          <p className={`mt-1 ${fieldHintClass}`}>
            {t("account_security.sessions.description", "Choose where to sign out.")}
          </p>
          <ul className={styles.sessionList}>
            {sessionChoices.map((choice) => (
              <li key={choice.scope} className={styles.sessionRow} data-scope={choice.scope}>
                <div className={styles.sessionCopy}>
                  <h3 className={styles.sessionTitle}>{choice.title}</h3>
                  <p id={`session-${choice.scope}-line`} className={styles.sessionHint}>
                    {choice.line}
                  </p>
                </div>
                <button
                  type="button"
                  disabled={disabled}
                  aria-label={choice.name}
                  aria-describedby={`session-${choice.scope}-line`}
                  onClick={choice.run}
                  className={`${choice.look} ${styles.sessionAction}`}
                >
                  {choice.action}
                </button>
              </li>
            ))}
          </ul>
          {outcomeFor("sessions")}
        </section>
      </div>

      <ConfirmDialog
        isOpen={confirmation !== null}
        tone={confirmation === "global" ? "danger" : "primary"}
        title={
          confirmation === "others"
            ? t("account_security.sessions.confirm_others_title", "Sign out other sessions?")
            : t("account_security.sessions.confirm_all_title", "Sign out everywhere?")
        }
        description={
          confirmation === "others"
            ? t(
                "account_security.sessions.confirm_others_description",
                "Other browsers will lose access. This browser stays signed in.",
              )
            : t(
                "account_security.sessions.confirm_all_description",
                "Every browser, including this one, will need a fresh login.",
              )
        }
        confirmLabel={t("common.confirm", "Confirm")}
        cancelLabel={t("common.cancel", "Cancel")}
        isBusy={busy !== null}
        error={confirmError}
        onCancel={() => {
          setConfirmation(null);
          setConfirmError(null);
        }}
        onConfirm={() => {
          if (confirmation) void signOut(confirmation);
        }}
      />
    </main>
  );
}
