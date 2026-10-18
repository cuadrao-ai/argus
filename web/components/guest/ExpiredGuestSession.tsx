"use client";

import { CuadraoLockup } from "@/components/CuadraoLockup";
import { guestLandingHref } from "@/lib/landing-entry";
import { postAuthPath } from "@/lib/landing-intent";
import { businessPilotEnabled } from "@/lib/private-alpha-flags";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import AuthForm, {
  type AuthFormMode,
} from "@/components/auth/AuthForm";
import {
  loginWithEmail,
  normalizeApiLanguage,
  signupWithEmail,
} from "@/lib/argus-api";
import {
  CAPTCHA_UNAVAILABLE_CODE,
  guestEntryErrorKind,
  type GuestEntryErrorKind,
} from "@/lib/guest-captcha";
import { retryGuestSession } from "@/lib/guest-session";
import { inlineFailureTextClass } from "@/lib/failure-treatment";

type ExpiredGuestSessionProps = {
  publicAccountAccessEnabled: boolean;
  /** Business has no guest mode: no new temporary chat is offered there. */
  businessBuild?: boolean;
};

export default function ExpiredGuestSession({
  publicAccountAccessEnabled,
  businessBuild = businessPilotEnabled,
}: ExpiredGuestSessionProps) {
  const { t, i18n } = useTranslation();
  const [authMode, setAuthMode] = useState<AuthFormMode | null>(null);
  const [isRestarting, setIsRestarting] = useState(false);
  const [restartErrorKind, setRestartErrorKind] =
    useState<GuestEntryErrorKind | null>(null);
  const captchaBlocked = restartErrorKind === CAPTCHA_UNAVAILABLE_CODE;

  const startNewTemporaryChat = async () => {
    setIsRestarting(true);
    setRestartErrorKind(null);
    try {
      await retryGuestSession(i18n.resolvedLanguage ?? i18n.language);
      window.location.assign(guestLandingHref(businessBuild));
    } catch (error) {
      const kind = guestEntryErrorKind(error);
      setRestartErrorKind(kind);
      if (kind === CAPTCHA_UNAVAILABLE_CODE) {
        setAuthMode(null);
      }
      setIsRestarting(false);
    }
  };

  return (
    <main className="flex min-h-[100dvh] items-center justify-center bg-background px-6 py-10 text-foreground">
      <section className="w-full max-w-md rounded-[20px] border border-black/10 bg-white p-7 dark:border-white/10 dark:bg-[#1d1f24] sm:p-9">
        <p className="flex justify-center" aria-label="Cuadrao">
          <CuadraoLockup width={160} />
        </p>
        <h1 className="mt-7 text-center text-2xl font-semibold tracking-tight">
          {t(
            "guest.expired.title",
            "This temporary chat has expired",
          )}
        </h1>
        <p className="mt-3 text-center text-sm leading-6 text-black/60 dark:text-white/60">
          {t(
            "guest.expired.detail",
            "Its messages and results can’t be recovered.",
          )}
        </p>

        {captchaBlocked ? (
          <div
            className="mt-7 flex flex-col items-center gap-3 text-center"
            role="alert"
          >
            <p className={`text-sm ${inlineFailureTextClass}`}>
              {t(
                "auth.errors.captcha_unavailable",
                "This browser didn’t pass the security check. Open Argus in a regular browser, or reload the page.",
              )}
            </p>
            <button
              type="button"
              className="min-h-11 rounded-full border border-current px-6 py-3 text-base font-medium"
              onClick={() => window.location.reload()}
            >
              {t("guest.entry.reload", "Reload")}
            </button>
          </div>
        ) : authMode ? (
          <div
            aria-label={
              authMode === "signup"
                ? t("guest.expired.create_account", "Create account")
                : t("guest.expired.sign_in", "Sign in")
            }
            className="mt-7"
            role="dialog"
          >
            <AuthForm
              mode={authMode}
              allowModeSwitch={publicAccountAccessEnabled}
              embedded
              onModeChange={setAuthMode}
              onSubmit={async ({ mode, displayName, email, password }) => {
                if (mode === "signup") {
                  const result = await signupWithEmail({
                    email,
                    password,
                    language: normalizeApiLanguage(
                      i18n.resolvedLanguage ?? i18n.language,
                    ),
                    display_name: displayName || null,
                  });
                  if (result.needsEmailConfirmation) {
                    return { status: "email_confirmation_required" as const };
                  }
                } else {
                  await loginWithEmail({ email, password });
                }
                // A signed-in person goes where sign-in goes: a listed return page, else the signed-in home.
                window.location.assign(postAuthPath(businessBuild));
              }}
              onEmailConfirmed={() => {
                window.location.assign(postAuthPath(businessBuild));
              }}
            />
            <button
              type="button"
              className="mt-4 min-h-11 w-full rounded-full border border-black/15 px-5 py-3 text-sm font-medium dark:border-white/20"
              onClick={() => setAuthMode(null)}
            >
              {t("common.back", "Back")}
            </button>
          </div>
        ) : (
          <div className="mt-7 grid gap-3">
            {businessBuild ? null : (
              <button
                type="button"
                disabled={isRestarting}
                onClick={() => void startNewTemporaryChat()}
                className="min-h-11 rounded-full bg-black px-6 py-3 text-base font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
              >
                {isRestarting
                  ? t("common.loading", "Loading...")
                  : t(
                      "guest.expired.start_new",
                      "Start a new temporary chat",
                    )}
              </button>
            )}
            <button
              type="button"
              className={
                businessBuild
                  ? "min-h-11 rounded-full bg-black px-6 py-3 text-base font-medium text-white dark:bg-white dark:text-black"
                  : "min-h-11 rounded-full border border-black/15 px-6 py-3 text-base font-medium dark:border-white/20"
              }
              onClick={() => setAuthMode("login")}
            >
              {t("guest.expired.sign_in", "Sign in")}
            </button>
            {publicAccountAccessEnabled && (
              <button
                type="button"
                className="min-h-11 rounded-full border border-black/15 px-6 py-3 text-base font-medium dark:border-white/20"
                onClick={() => setAuthMode("signup")}
              >
                {t("guest.expired.create_account", "Create account")}
              </button>
            )}
          </div>
        )}

        {restartErrorKind === "generic" && (
          <p className={`mt-4 text-center text-sm ${inlineFailureTextClass}`} role="alert">
            {t(
              "guest.expired.restart_error",
              "Argus could not start a new temporary chat. Try again.",
            )}
          </p>
        )}
      </section>
    </main>
  );
}
