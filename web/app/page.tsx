"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
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
  normalizeApiLanguage,
  signupWithEmail,
} from "@/lib/argus-api";
import { guestAccessEnabled } from "@/lib/private-alpha-flags";
import {
  resolveLandingEntrySurface,
} from "@/lib/landing-entry";
import {
  captureLandingIntentFromLocation,
  postAuthPath,
} from "@/lib/landing-intent";
import { guestCaptchaConfigured } from "@/lib/guest-session";
import { guestProfileProbeOutcome } from "@/lib/guest-account";

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
  const [businessEntry, setBusinessEntry] = useState(false);
  const [authMode, setAuthMode] = useState<AuthMode>("intro");
  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const [profileProbeFailedClosed, setProfileProbeFailedClosed] =
    useState(false);

  useEffect(() => {
    captureLandingIntentFromLocation();
    setBusinessEntry(postAuthPath().split("?")[0] === "/biz");
    const nextAuthMode = authModeFromLocation();
    setAuthMode(nextAuthMode);
    if (skipAuthenticatedRedirect()) {
      setIsCheckingSession(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const meResponse = await getMe();
        if (cancelled) return;
        if (meResponse === null) {
          setProfileProbeFailedClosed(true);
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
    }

    router.replace(postAuthPath());
    router.refresh();
  };

  const isSignup = authMode === "signup";
  const entrySurface = resolveLandingEntrySurface({
    authMode,
    guestEntryAvailable:
      !profileProbeFailedClosed && guestAccessEnabled && guestCaptchaConfigured,
    isCheckingSession,
  });

  if (entrySurface === "loading") {
    return (
      <>
        <DevModeBadge />
        <div className="flex h-[100dvh] w-full items-center justify-center bg-background">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      </>
    );
  }

  if (entrySurface === "guest") {
    return <GuestEntry />;
  }

  return (
    <>
      <DevModeBadge />
      <main className={`relative flex min-h-[100dvh] w-full flex-col justify-between overflow-hidden px-6 py-8 md:px-12 ${businessEntry ? "bg-[#fafbf8] dark:bg-[#172b26]" : ""}`}>
        <SettingsMenu />

        <div className="flex flex-grow items-center justify-center">
          {businessEntry ? (
            <h1 className="z-10 w-[268px] max-w-full select-none" aria-label="Cuadrao">
              <Image unoptimized loading="eager" src="/brand/cuadrao-lockup-light.svg" alt="" width={268} height={56} className="h-auto w-full dark:hidden" />
              <Image unoptimized loading="eager" src="/brand/cuadrao-lockup-dark.svg" alt="" width={268} height={56} className="hidden h-auto w-full dark:block" />
            </h1>
          ) : (
            <h1 className="font-display text-6xl md:text-[80px] font-medium tracking-tight text-black dark:text-white z-10 select-none transition-colors">
              argus
            </h1>
          )}
        </div>

        <div className="relative z-10 flex w-full flex-col items-center gap-6 pb-2 md:pb-4">
          {authMode === "intro" ? (
            <button
              type="button"
              onClick={showRequest}
              className="font-display flex w-full max-w-sm items-center justify-center rounded-[9999px] bg-black px-[32px] py-[14px] text-[16px] font-medium text-white transition-opacity hover:opacity-85 focus:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black dark:bg-white dark:text-black dark:focus-visible:ring-white"
            >
              {t("auth.access_request.submit")}
            </button>
          ) : (
            <div className="w-full max-w-sm">
              {authMode === "request" ? (
                <RequestAccess
                  onShowSignup={showSignup}
                  onShowLogin={showLogin}
                />
              ) : (
                <AuthForm
                  mode={isSignup ? "signup" : "login"}
                  brand={businessEntry ? "cuadrao" : "argus"}
                  onModeChange={(mode) => updateAuthMode(mode)}
                  onSubmit={handleAuthSubmit}
                />
              )}
            </div>
          )}

          {authMode === "intro" && (
            <>
              <p className="text-[16px] tracking-wide text-gray-500 dark:text-gray-400">
                {t('landing.already_account')}{" "}
                <button
                  type="button"
                  className="font-medium text-black transition-opacity hover:opacity-80 dark:text-white"
                  onClick={showLogin}
                >
                  {t('landing.sign_in')}
                </button>
              </p>

              <p className="mt-4 w-full px-4 text-center text-[11px] md:text-[12px] text-zinc-500 tracking-tight">
                {t('landing.legal_prefix', 'By joining, you agree to our')}{" "}
                <a href="/terms" className="font-semibold text-zinc-800 dark:text-zinc-400 hover:text-black dark:hover:text-white transition-colors">
                  {t('landing.terms')}
                </a>{" "}
                {t('common.and', 'and')}{" "}
                <a href="/privacy" className="font-semibold text-zinc-800 dark:text-zinc-400 hover:text-black dark:hover:text-white transition-colors">
                  {t('landing.privacy')}
                </a>.
              </p>
            </>
          )}
        </div>
      </main>
    </>
  );
}
