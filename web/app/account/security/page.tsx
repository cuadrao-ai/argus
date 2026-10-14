"use client";

import {
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import Link from "next/link";
import { signedInHomePath } from "@/lib/landing-intent";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import {
  accountSecurityLoadFailureAction,
  getAuthSecurityActions,
  type SessionActionResult,
} from "@/lib/auth-security";
import { getMe } from "@/lib/argus-api";

type Confirmation = "others" | "all" | null;
type AuthCheckState = "checking" | "ready" | "unavailable";

export default function AccountSecurityPage() {
  const { t } = useTranslation();
  const authChecked = useRef(false);
  const [authCheckState, setAuthCheckState] =
    useState<AuthCheckState>("checking");
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [freshLogin, setFreshLogin] = useState(false);

  const checkSession = useCallback(() => {
    setAuthCheckState("checking");
    getMe()
      .then(() => setAuthCheckState("ready"))
      .catch((loadError: unknown) => {
        if (accountSecurityLoadFailureAction(loadError) === "redirect_to_login") {
          window.location.replace("/?auth=login");
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
    result: SessionActionResult,
    successMessage: string,
    revocationWarning: string,
  ) => {
    setMessage(null);
    setWarning(null);
    if (result.revocation === "failed") {
      setWarning(revocationWarning);
    } else if (result.cookieSync === "failed") {
      setWarning(
        t(
          "account_security.cookie_sync_warning",
          "Sessions were revoked, but local cookie cleanup could not be confirmed.",
        ),
      );
    } else {
      setMessage(successMessage);
    }
    setFreshLogin(result.freshLoginRequired);
  };

  const changePassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setWarning(null);
    if (newPassword !== confirmPassword) {
      setError(t("auth.recovery.password_mismatch", "Passwords do not match."));
      return;
    }
    setBusy("password");
    try {
      const result = await getAuthSecurityActions().changePassword({
        currentPassword,
        newPassword,
      });
      applyResult(
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
    } catch {
      setError(
        t(
          "account_security.password.error",
          "We couldn’t change the password. Check your current password and try again.",
        ),
      );
    } finally {
      setBusy(null);
    }
  };

  const signOut = async (scope: "local" | "others" | "global") => {
    setConfirmation(null);
    setError(null);
    setMessage(null);
    setWarning(null);
    setBusy(scope);
    try {
      const actions = getAuthSecurityActions();
      const result =
        scope === "local"
          ? await actions.signOutThisBrowser()
          : scope === "others"
            ? await actions.signOutOtherSessions()
            : await actions.signOutAllSessions();
      applyResult(
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
      setError(
        t(
          "account_security.sessions.error",
          "We couldn’t complete that session change. Try again.",
        ),
      );
    } finally {
      setBusy(null);
    }
  };

  if (authCheckState !== "ready") {
    return (
      <main className="flex min-h-[100dvh] items-center justify-center px-6 text-sm text-black/55 dark:text-white/55">
        {authCheckState === "checking" ? (
          t("account_security.loading", "Checking your session...")
        ) : (
          <div className="max-w-sm text-center">
            <p role="alert">
              {t(
                "account_security.session_check_unavailable",
                "Cuadrao couldn’t verify your session right now. Try again.",
              )}
            </p>
            <button
              type="button"
              onClick={checkSession}
              className="mt-4 rounded-full bg-black px-5 py-3 font-medium text-white dark:bg-white dark:text-black"
            >
              {t("account_security.retry", "Retry")}
            </button>
          </div>
        )}
      </main>
    );
  }

  return (
    <main className="min-h-[100dvh] px-6 py-10 md:px-12">
      <div className="mx-auto w-full max-w-2xl">
        <Link href={signedInHomePath()} className="text-sm font-medium text-black/55 hover:text-black dark:text-white/55 dark:hover:text-white">
          {t("account_security.back", "Back to Cuadrao")}
        </Link>
        <h1 className="mt-6 font-display text-4xl font-medium tracking-tight text-black dark:text-white">
          {t("account_security.title", "Account security")}
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-black/55 dark:text-white/55">
          {t(
            "account_security.description",
            "Change your password or choose exactly which sessions to sign out.",
          )}
        </p>

        {message && (
          <p role="status" className="mt-6 rounded-[18px] border border-emerald-500/20 bg-emerald-500/[0.06] p-4 text-sm text-emerald-800 dark:text-emerald-200">
            {message}
          </p>
        )}
        {warning && (
          <p role="alert" className="mt-6 rounded-[18px] border border-amber-500/20 bg-amber-500/[0.06] p-4 text-sm text-amber-800 dark:text-amber-200">
            {warning}
          </p>
        )}
        {error && (
          <p role="alert" className="mt-6 rounded-[18px] border border-red-500/20 bg-red-500/[0.05] p-4 text-sm text-red-700 dark:text-red-200">
            {error}
          </p>
        )}
        {freshLogin && (
          <Link href="/?auth=login" className="mt-4 inline-flex rounded-full bg-black px-5 py-3 text-sm font-medium text-white dark:bg-white dark:text-black">
            {t("auth.recovery.back_to_sign_in", "Back to sign in")}
          </Link>
        )}

        <section className="mt-8 rounded-[24px] border border-black/10 bg-white p-6 dark:border-white/10 dark:bg-[#151719]">
          <h2 className="font-display text-xl font-medium text-black dark:text-white">
            {t("account_security.password.title", "Change password")}
          </h2>
          <p className="mt-1 text-sm text-black/55 dark:text-white/55">
            {t(
              "account_security.password.description",
              "Enter your current password. After the change, every browser must sign in again.",
            )}
          </p>
          <form onSubmit={changePassword} className="mt-5 space-y-4">
            {[
              {
                label: t("account_security.password.current", "Current password"),
                value: currentPassword,
                setValue: setCurrentPassword,
                autoComplete: "current-password",
              },
              {
                label: t("account_security.password.new", "New password"),
                value: newPassword,
                setValue: setNewPassword,
                autoComplete: "new-password",
              },
              {
                label: t("account_security.password.confirm", "Confirm new password"),
                value: confirmPassword,
                setValue: setConfirmPassword,
                autoComplete: "new-password",
              },
            ].map((field) => (
              <label key={field.label} className="block text-sm font-medium text-black dark:text-white">
                {field.label}
                <input
                  type="password"
                  required
                  minLength={field.autoComplete === "new-password" ? 8 : undefined}
                  autoComplete={field.autoComplete}
                  value={field.value}
                  onChange={(event) => field.setValue(event.target.value)}
                  className="mt-2 w-full rounded-[18px] border border-black/15 bg-transparent px-4 py-3 text-base outline-none focus-visible:ring-2 focus-visible:ring-black dark:border-white/20 dark:focus-visible:ring-white"
                />
              </label>
            ))}
            <button type="submit" disabled={busy !== null || freshLogin} className="rounded-full bg-black px-5 py-3 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black">
              {busy === "password"
                ? t("account_security.password.changing", "Changing...")
                : t("account_security.password.submit", "Change password")}
            </button>
          </form>
        </section>

        <section className="mt-5 rounded-[24px] border border-black/10 bg-white p-6 dark:border-white/10 dark:bg-[#151719]">
          <h2 className="font-display text-xl font-medium text-black dark:text-white">
            {t("account_security.sessions.title", "Sessions")}
          </h2>
          <p className="mt-1 text-sm text-black/55 dark:text-white/55">
            {t(
              "account_security.sessions.description",
              "Choose whether to keep this browser signed in.",
            )}
          </p>
          <div className="mt-5 flex flex-col gap-3">
            <button type="button" disabled={busy !== null || freshLogin} onClick={() => void signOut("local")} className="rounded-[18px] border border-black/10 px-4 py-3 text-left text-sm font-medium text-black hover:bg-black/[0.03] disabled:opacity-50 dark:border-white/10 dark:text-white dark:hover:bg-white/[0.04]">
              {t("account_security.sessions.sign_out_this", "Sign out this browser")}
            </button>
            <button type="button" disabled={busy !== null || freshLogin} onClick={() => setConfirmation("others")} className="rounded-[18px] border border-black/10 px-4 py-3 text-left text-sm font-medium text-black hover:bg-black/[0.03] disabled:opacity-50 dark:border-white/10 dark:text-white dark:hover:bg-white/[0.04]">
              {t("account_security.sessions.sign_out_others", "Sign out other sessions")}
            </button>
            <button type="button" disabled={busy !== null || freshLogin} onClick={() => setConfirmation("all")} className="rounded-[18px] border border-red-500/20 px-4 py-3 text-left text-sm font-medium text-red-700 hover:bg-red-500/[0.04] disabled:opacity-50 dark:text-red-200">
              {t("account_security.sessions.sign_out_all", "Sign out all sessions")}
            </button>
          </div>
        </section>
      </div>

      <ConfirmDialog
        isOpen={confirmation !== null}
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
        onCancel={() => setConfirmation(null)}
        onConfirm={() => void signOut(confirmation === "others" ? "others" : "global")}
      />
    </main>
  );
}
