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
import { AlertCircle, ChevronLeft, CircleCheck } from "lucide-react";
import { signedInHomePath } from "@/lib/landing-intent";
import { useTranslation } from "react-i18next";

import {
  primaryButtonClass,
  quietButtonClass,
  secondaryButtonClass,
} from "@/components/business-app/business-ui";
import { SURFACE_CARD } from "@/components/business-app/foundation/surfaces";
import { BusinessClosedNotice } from "@/components/status/BusinessClosedNotice";
import { ServerErrorScreen } from "@/components/status/ServerErrorScreen";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import {
  fieldClass,
  fieldErrorClass,
  fieldHintClass,
  fieldLabelClass,
} from "@/components/ui/form-field";
import {
  accountSecurityLoadFailureAction,
  getAuthSecurityActions,
  type SessionActionResult,
} from "@/lib/auth-security";
import { getMe } from "@/lib/argus-api";
import { referenceCode, runQuietRetries, sessionEndedLoginPath } from "@/lib/failure-screen";

type SignOutScope = "local" | "others" | "global";
type Confirmation = Exclude<SignOutScope, "local"> | null;
type Section = "password" | "sessions";
type Busy = "password" | SignOutScope | null;
type AuthCheckState = "checking" | "ready" | "unavailable" | "closed" | "server";
/** What the last action left on screen, shown inside the section it came from. */
type Outcome =
  | { kind: "done"; section: Section; text: string }
  | { kind: "warning" | "error"; section: Section; text: string; retry: SignOutScope | "password" };

const MIN_PASSWORD_LENGTH = 8;

export default function AccountSecurityPage() {
  const { t } = useTranslation();
  const authChecked = useRef(false);
  const passwordForm = useRef<HTMLFormElement>(null);
  const [authCheckState, setAuthCheckState] =
    useState<AuthCheckState>("checking");
  const [busy, setBusy] = useState<Busy>(null);
  const [confirmation, setConfirmation] = useState<Confirmation>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [checkFields, setCheckFields] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [freshLogin, setFreshLogin] = useState(false);
  const [reference, setReference] = useState("");

  const tooShort = checkFields && newPassword.length < MIN_PASSWORD_LENGTH;
  const mismatch = checkFields && newPassword !== confirmPassword;
  const fieldsFilled = Boolean(currentPassword && newPassword && confirmPassword);

  const checkSession = useCallback(() => {
    setAuthCheckState("checking");
    runQuietRetries(() => getMe())
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
  }, []);

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
        retry,
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
    setOutcome(null);
    setCheckFields(true);
    if (newPassword.length < MIN_PASSWORD_LENGTH || newPassword !== confirmPassword) return;
    setBusy("password");
    try {
      const result = await getAuthSecurityActions().changePassword({
        currentPassword,
        newPassword,
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
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setCheckFields(false);
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
      setBusy(null);
    }
  };

  const signOut = async (scope: SignOutScope) => {
    const fromConfirmation = scope !== "local" && confirmation !== null;
    setConfirmError(null);
    setOutcome(null);
    setBusy(scope);
    try {
      const actions = getAuthSecurityActions();
      const result =
        scope === "local"
          ? await actions.signOutThisBrowser()
          : scope === "others"
            ? await actions.signOutOtherSessions()
            : await actions.signOutAllSessions();
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

  const retry = (target: SignOutScope | "password") => {
    if (target === "password") passwordForm.current?.requestSubmit();
    else void signOut(target);
  };

  const retryLabel = t("account_security.retry", "Retry");
  const outcomeFor = (section: Section): ReactNode => {
    if (outcome?.section !== section) return null;
    if (outcome.kind === "done") {
      return (
        <div className="mt-[21px] space-y-[13px]">
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
      <div role="alert" className={`mt-[21px] rounded-item px-4 py-3 text-[15px] leading-relaxed ${tone}`}>
        <p className="flex items-start gap-2">
          <AlertCircle className="mt-1 h-4 w-4 shrink-0" aria-hidden="true" />
          {outcome.text}
        </p>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => retry(outcome.retry)}
          className={`${quietButtonClass} ml-6`}
        >
          {retryLabel}
        </button>
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
  const passwordFields = [
    {
      id: "current-password",
      label: t("account_security.password.current", "Current password"),
      value: currentPassword,
      setValue: setCurrentPassword,
      autoComplete: "current-password",
      error: null,
    },
    {
      id: "new-password",
      label: t("account_security.password.new", "New password"),
      value: newPassword,
      setValue: setNewPassword,
      autoComplete: "new-password",
      error: tooShort
        ? t("account_security.password.too_short", "Use at least 8 characters.")
        : null,
    },
    {
      id: "confirm-password",
      label: t("account_security.password.confirm", "Confirm new password"),
      value: confirmPassword,
      setValue: setConfirmPassword,
      autoComplete: "new-password",
      error: !tooShort && mismatch
        ? t("auth.recovery.password_mismatch", "Passwords do not match.")
        : null,
    },
  ];

  return (
    <main className="business-foundation min-h-[100dvh] bg-[#F7F5EE] px-4 py-8 text-[#172b26] dark:bg-[#141517] dark:text-white tablet:px-8 tablet:py-[55px]">
      <div className="mx-auto w-full max-w-[40rem]">
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

        <section aria-labelledby="password-title" className={`mt-[34px] ${SURFACE_CARD}`}>
          <h2 id="password-title" className="font-display text-[21px] font-medium">
            {t("account_security.password.title", "Change password")}
          </h2>
          <p className={`mt-1 ${fieldHintClass}`}>
            {t(
              "account_security.password.description",
              "Enter your current password. After the change, every browser must sign in again.",
            )}
          </p>
          <form ref={passwordForm} noValidate onSubmit={changePassword} className="mt-[21px] space-y-[21px]">
            {passwordFields.map((field) => (
              <div key={field.id}>
                <label htmlFor={field.id} className={fieldLabelClass}>
                  {field.label}
                </label>
                <input
                  id={field.id}
                  type="password"
                  autoComplete={field.autoComplete}
                  value={field.value}
                  aria-invalid={field.error ? true : undefined}
                  aria-describedby={field.error ? `${field.id}-error` : undefined}
                  onChange={(event) => field.setValue(event.target.value)}
                  className={fieldClass}
                />
                {field.error && (
                  <p id={`${field.id}-error`} role="alert" className={`mt-2 ${fieldErrorClass}`}>
                    {field.error}
                  </p>
                )}
              </div>
            ))}
            <button type="submit" disabled={disabled || !fieldsFilled} className={primaryButtonClass}>
              {busy === "password"
                ? t("account_security.password.changing", "Changing...")
                : t("account_security.password.submit", "Change password")}
            </button>
          </form>
          {outcomeFor("password")}
        </section>

        <section aria-labelledby="sessions-title" className={`mt-[21px] ${SURFACE_CARD}`}>
          <h2 id="sessions-title" className="font-display text-[21px] font-medium">
            {t("account_security.sessions.title", "Sessions")}
          </h2>
          <p className={`mt-1 ${fieldHintClass}`}>
            {t(
              "account_security.sessions.description",
              "Choose whether to keep this browser signed in.",
            )}
          </p>
          <div className="mt-[21px] flex flex-col items-start gap-[13px]">
            <button type="button" disabled={disabled} onClick={() => void signOut("local")} className={secondaryButtonClass}>
              {t("account_security.sessions.sign_out_this", "Sign out this browser")}
            </button>
            <button type="button" disabled={disabled} onClick={() => setConfirmation("others")} className={secondaryButtonClass}>
              {t("account_security.sessions.sign_out_others", "Sign out other sessions")}
            </button>
            <button type="button" disabled={disabled} onClick={() => setConfirmation("global")} className={secondaryButtonClass}>
              {t("account_security.sessions.sign_out_all", "Sign out all sessions")}
            </button>
          </div>
          {outcomeFor("sessions")}
        </section>
      </div>

      <ConfirmDialog
        isOpen={confirmation !== null}
        tone="primary"
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
