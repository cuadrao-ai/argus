"use client";

import { useEffect, useState } from "react";
import FullscreenLoading from "@/components/FullscreenLoading";
import { CuadraoLockup } from "@/components/CuadraoLockup";
import { useRouter } from "next/navigation";
import AuthForm, {
  type AuthFormSubmission,
} from "@/components/auth/AuthForm";
import RequestAccess from "@/components/auth/RequestAccess";
import { SettingsMenu } from "@/components/SettingsMenu";
import GuestEntry from "@/components/guest/GuestEntry";
import { useTranslation } from "react-i18next";
import { DevModeBadge } from "@/components/ui/DevModeBadge";
import {
  getMe,
  loginWithEmail,
  logoutFromApi,
  normalizeApiLanguage,
  signupWithEmail,
} from "@/lib/argus-api";
import { businessPilotEnabled, guestAccessEnabled } from "@/lib/private-alpha-flags";
import {
  guestEntryAvailable,
  resolveLandingEntrySurface,
  sessionAdmitted,
} from "@/lib/landing-entry";
import {
  captureLandingIntentFromLocation,
  postAuthPath,
} from "@/lib/landing-intent";
import { guestCaptchaConfigured } from "@/lib/guest-session";
import { ENABLED_LANGUAGES, normalizeEnabledLanguage, type ArgusLanguage } from "@/lib/language-features";
import { saveProfileLanguage } from "@/lib/profile-writes";
import { guestProfileProbeOutcome } from "@/lib/guest-account";
import { completeAuthVerification } from "@/lib/auth-verification";
import { acceptanceLinks } from "@/lib/cuadrao-legal-links";

type AuthMode = "intro" | "request" | "signup" | "login";

function authModeFromLocation(): AuthMode {
  if (typeof window === "undefined") return "intro";
  const mode = new URLSearchParams(window.location.search).get("auth");
  return mode === "request" || mode === "signup" || mode === "login"
    ? mode
    : "intro";
}

function skipAuthenticatedRedirect(): boolean {
  if (typeof window === "undefined") return true;
  const params = new URLSearchParams(window.location.search);
  const authMode = params.get("auth");
  return (
    params.get("preview") === "true" ||
    authMode === "request" ||
    authMode === "signup" ||
    authMode === "login"
  );
}

export default function LandingPage() {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const isMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH === "true";
  const [authMode, setAuthMode] = useState<AuthMode>("intro");
  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const [verificationFailed, setVerificationFailed] = useState(false);
  const [profileProbeFailedClosed, setProfileProbeFailedClosed] =
    useState(false);

  useEffect(() => {
    captureLandingIntentFromLocation();
    const nextAuthMode = authModeFromLocation();
    setAuthMode(nextAuthMode);
    const verification = completeAuthVerification();
    let cancelled = false;
    (async () => {
      try {
        const verified = await verification;
        if (cancelled) return;
        if (verified === "failed") {
          setVerificationFailed(true);
          setAuthMode("login");
          setIsCheckingSession(false);
          return;
        }
        if (verified === "none" && skipAuthenticatedRedirect()) {
          setIsCheckingSession(false);
          return;
        }
        const meResponse = await getMe();
        if (cancelled) return;
        if (meResponse === null) {
          setProfileProbeFailedClosed(true);
          setIsCheckingSession(false);
          return;
        }
        if (!sessionAdmitted(meResponse.account_kind, businessPilotEnabled)) {
          // Business has no guest mode: the guest session is ended here so it
          // cannot bounce between the front door and the Business shell.
          await logoutFromApi().catch(() => undefined);
          if (cancelled) return;
          setIsCheckingSession(false);
          return;
        }
        router.replace(postAuthPath());
      } catch (error) {
        if (cancelled) return;
        setProfileProbeFailedClosed(
          guestProfileProbeOutcome(error) === "fail_closed",
        );
        setIsCheckingSession(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  const updateAuthMode = (nextMode: AuthMode) => {
    setAuthMode(nextMode);
    if (typeof window === "undefined") return;

    const params = new URLSearchParams(window.location.search);
    if (nextMode === "intro") {
      params.delete("auth");
    } else {
      params.set("auth", nextMode);
    }

    const query = params.toString();
    const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
    window.history.replaceState(null, "", nextUrl);
  };
  // A language chosen on this page before signing in. It is shown at once and,
  // once the account signs in, saved on it; the account's own setting rules
  // every later visit.
  const [chosenLanguage, setChosenLanguage] = useState<ArgusLanguage | null>(null);
  const shownLanguage = normalizeEnabledLanguage(i18n.resolvedLanguage ?? i18n.language);
  const otherLanguages = ENABLED_LANGUAGES.filter((language) => language.code !== shownLanguage);
  const chooseLanguage = async (code: ArgusLanguage) => {
    await i18n.changeLanguage(code);
    setChosenLanguage(code);
  };
  const showRequest = () => updateAuthMode("request");
  const showSignup = () => updateAuthMode("signup");
  const showLogin = () => updateAuthMode("login");

  const handleAuthSubmit = async (submission: AuthFormSubmission) => {
    const allowMockSignupNetwork =
      process.env.NEXT_PUBLIC_E2E_ALLOW_MOCK_SIGNUP === "true" &&
      submission.mode === "signup";
    if (isMockAuth && !allowMockSignupNetwork) {
      router.replace(postAuthPath());
      router.refresh();
      return;
    }

    if (submission.mode === "signup") {
      const result = await signupWithEmail({
        email: submission.email,
        password: submission.password,
        language: normalizeApiLanguage(i18n.resolvedLanguage ?? i18n.language),
        display_name: submission.displayName || null,
      });
      if (result.needsEmailConfirmation) {
        return { status: "email_confirmation_required" as const };
      }
    } else {
      await loginWithEmail({
        email: submission.email,
        password: submission.password,
      });
      // The choice made on this page outlives the sign-in: saved on the
      // account now, so the workspace does not switch back to the account's
      // earlier language. A failed save keeps the shown language for this visit.
      if (chosenLanguage) {
        await saveProfileLanguage(i18n, chosenLanguage, { onSaved: () => undefined }).catch(() => false);
      }
    }

    router.replace(postAuthPath());
    router.refresh();
  };

  const isSignup = authMode === "signup";
  const acceptance = acceptanceLinks();
  const entrySurface = resolveLandingEntrySurface({
    authMode,
    // A Business build has no guest chat: a signed-out visitor sees login.
    guestEntryAvailable: guestEntryAvailable({ businessBuild: businessPilotEnabled, probeFailedClosed: profileProbeFailedClosed, guestAccessEnabled, guestCaptchaConfigured }),
    isCheckingSession,
  });

  if (entrySurface === "loading") {
    return (
      <>
        <DevModeBadge />
        <FullscreenLoading />
      </>
    );
  }

  if (entrySurface === "guest") {
    return <GuestEntry />;
  }

  return (
    <>
      <DevModeBadge />
      <main className="relative flex min-h-[100dvh] w-full flex-col justify-between overflow-hidden bg-[#fafbf8] px-6 py-8 md:px-12 dark:bg-[#172b26]">
        <SettingsMenu />

        <div className="flex flex-grow items-center justify-center">
          <h1 className="z-10 max-w-full select-none" aria-label="Cuadrao">
            <CuadraoLockup width={268} />
          </h1>
        </div>

        <div data-auth-brand="cuadrao" className="relative z-10 flex w-full flex-col items-center gap-6 pb-2 md:pb-4">
          {authMode === "intro" ? (
            <button
              type="button"
              onClick={showRequest}
              data-testid="landing-request-access"
              className="font-display flex w-full max-w-sm items-center justify-center rounded-[9999px] bg-[#2f5a49] px-[32px] py-[14px] text-[16px] font-medium !text-[#fafbf8] transition-opacity hover:opacity-85 focus:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-[#2f5a49] dark:bg-[#abd4bf] dark:!text-[#172b26] dark:focus-visible:ring-[#abd4bf]"
            >
              {t("auth.access_request.submit")}
            </button>
          ) : (
            <div className="w-full max-w-sm">
              {verificationFailed ? <p role="alert">{t("auth.errors.unauthorized", "We couldn’t verify those account details. Check them and try again.")}</p> : null}
              {authMode === "request" ? (
                <RequestAccess
                  onShowSignup={showSignup}
                  onShowLogin={showLogin}
                />
              ) : (
                <AuthForm
                  mode={isSignup ? "signup" : "login"}
                  brand="cuadrao"
                  onModeChange={(mode) => updateAuthMode(mode)}
                  onSubmit={handleAuthSubmit}
                />
              )}
            </div>
          )}

          {otherLanguages.length > 0 ? (
            <p className="text-[13px] tracking-wide text-black/60 dark:text-white/60" data-testid="auth-language-switch">
              {otherLanguages.map((language) => (
                <button
                  key={language.code}
                  type="button"
                  lang={language.code}
                  className="min-h-11 rounded-full px-3 font-medium underline-offset-4 transition-opacity hover:opacity-80 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2f5a49]/40"
                  onClick={() => void chooseLanguage(language.code)}
                >
                  {language.name}
                </button>
              ))}
            </p>
          ) : null}

          {authMode === "intro" && (
            <>
              <p className="text-[16px] tracking-wide">
                {t('landing.already_account')}{" "}
                <button
                  type="button"
                  className="font-medium transition-opacity hover:opacity-80"
                  onClick={showLogin}
                >
                  {t('landing.sign_in')}
                </button>
              </p>

              {acceptance ? (
                <p className="mt-4 w-full px-4 text-center text-[11px] md:text-[12px] tracking-tight">
                  {t('landing.legal_prefix', 'By joining, you agree to our')}{" "}
                  <a href={acceptance.terms} className="font-semibold transition-opacity hover:opacity-80">
                    {t('landing.terms')}
                  </a>{" "}
                  {t('common.and', 'and')}{" "}
                  <a href={acceptance.privacy} className="font-semibold transition-opacity hover:opacity-80">
                    {t('landing.privacy')}
                  </a>.
                </p>
              ) : null}
            </>
          )}
        </div>
      </main>
    </>
  );
}
