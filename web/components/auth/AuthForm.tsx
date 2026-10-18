"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import { Eye, EyeClosed } from "lucide-react";
import { useTranslation } from "react-i18next";
import { acceptanceLinks } from "@/lib/cuadrao-legal-links";
import {
  EmailOtpRejectedError,
  normalizeEmailOtp,
  verifyEmailOtp,
} from "@/lib/email-otp";
import { blockingErrorBannerClass } from "@/lib/failure-treatment";

export type AuthFormMode = "login" | "signup";

export type AuthFormSubmission = {
  mode: AuthFormMode;
  displayName: string;
  email: string;
  password: string;
};

export type AuthFormSubmissionResult = {
  status: "email_confirmation_required";
};

type AuthFormProps = {
  mode: AuthFormMode;
  brand?: "argus" | "cuadrao";
  allowModeSwitch?: boolean;
  embedded?: boolean;
  onModeChange?: (mode: AuthFormMode) => void;
  onSubmit: (
    submission: AuthFormSubmission,
  ) => Promise<AuthFormSubmissionResult | void>;
  onConfirmEmailCode?: (input: { email: string; code: string }) => Promise<void>;
  onEmailConfirmed?: () => void | Promise<void>;
};

type AuthErrorTranslation = Readonly<{
  key: string;
  fallback: string;
}>;

type AuthErrorTranslator = (key: string, fallback: string) => string;

const GENERIC_AUTH_ERROR: AuthErrorTranslation = {
  key: "auth.errors.generic",
  fallback: "Something went wrong. Please try again.",
};

const AUTH_ERROR_MESSAGE_BY_CODE: Readonly<
  Record<string, AuthErrorTranslation>
> = {
  captcha_unavailable: {
    key: "auth.errors.browser_check_failed",
    fallback: "We couldn’t verify your browser. Try again.",
  },
  unauthorized: {
    key: "auth.errors.unauthorized",
    fallback:
      "We couldn’t verify those account details. Check them and try again.",
  },
  auth_signup_failed: {
    key: "auth.errors.auth_signup_failed",
    fallback: "We couldn’t create the account. Please try again.",
  },
  too_many_requests: {
    key: "auth.errors.too_many_requests",
    fallback: "Too many attempts. Wait a moment and try again.",
  },
  guest_access_unavailable: {
    key: "auth.errors.guest_access_unavailable",
    fallback: "Guest access isn’t available right now.",
  },
  internal_error: {
    key: "auth.errors.internal_error",
    fallback: "Cuadrao couldn’t complete this account request. Please try again.",
  },
  account_already_registered: {
    key: "auth.errors.account_already_registered",
    fallback: "This session already belongs to a permanent account.",
  },
  account_exists_use_login: {
    key: "auth.errors.account_exists_use_login",
    fallback:
      "You already have an account. Sign in instead and your conversation comes with you.",
  },
  guest_bootstrap_failed: {
    key: "auth.errors.guest_bootstrap_failed",
    fallback: "We couldn’t start a temporary conversation. Please try again.",
  },
  guest_identity_link_failed: {
    key: "auth.errors.guest_identity_link_failed",
    fallback:
      "We couldn’t finish creating the account. Your conversation is safe; try again.",
  },
  csrf_origin_rejected: {
    key: "auth.errors.csrf_origin_rejected",
    fallback: "We couldn’t verify this request. Refresh the page and try again.",
  },
  registered_account_required: {
    key: "auth.errors.registered_account_required",
    fallback: "Sign in to claim this temporary conversation.",
  },
  access_request_unavailable: {
    key: "auth.errors.access_request_unavailable",
    fallback: "We couldn’t send your access request. Please try again.",
  },
  public_account_access_unavailable: {
    key: "auth.errors.public_account_access_unavailable",
    fallback: "Account creation isn’t available right now.",
  },
  guest_session_expired: {
    key: "auth.errors.guest_session_expired",
    fallback: "This temporary session has expired. Start a new one or sign in.",
  },
  guest_handoff_invalid: {
    key: "auth.errors.guest_handoff_invalid",
    fallback:
      "This conversation transfer is no longer valid. Please try signing in again.",
  },
  guest_handoff_consumed: {
    key: "auth.errors.guest_handoff_consumed",
    fallback: "This temporary conversation has already been claimed.",
  },
  guest_handoff_expired: {
    key: "auth.errors.guest_handoff_expired",
    fallback: "The transfer expired. Start the sign-in flow again.",
  },
  guest_handoff_wrong_destination: {
    key: "auth.errors.guest_handoff_wrong_destination",
    fallback:
      "Sign in with the account this temporary conversation was sent to.",
  },
  guest_handoff_source_not_anonymous: {
    key: "auth.errors.guest_handoff_source_not_anonymous",
    fallback: "This conversation no longer belongs to a temporary account.",
  },
  guest_handoff_unsafe_product_graph: {
    key: "auth.errors.guest_handoff_unsafe_product_graph",
    fallback:
      "We couldn’t transfer this conversation safely. Your original conversation is unchanged.",
  },
  guest_handoff_workspace_unavailable: {
    key: "auth.errors.guest_handoff_workspace_unavailable",
    fallback: "This temporary conversation is no longer available.",
  },
  guest_handoff_claim_unavailable: {
    key: "auth.errors.guest_handoff_claim_unavailable",
    fallback:
      "We couldn’t claim the temporary conversation right now. Please try again.",
  },
  otp_rejected: {
    key: "auth.errors.otp_rejected",
    fallback: "That code was not accepted. Check the email and try again.",
  },
};

function authErrorCode(error: unknown): string {
  if (!(error instanceof Error) || !("code" in error)) return "";
  const code = (error as Error & { code?: unknown }).code;
  return typeof code === "string" ? code : "";
}

export function localizedAuthErrorMessage(
  error: unknown,
  translate: AuthErrorTranslator,
): string {
  const message =
    AUTH_ERROR_MESSAGE_BY_CODE[authErrorCode(error)] ?? GENERIC_AUTH_ERROR;
  return translate(message.key, message.fallback);
}

const LEGAL_LINK_CLASS =
  "font-semibold text-zinc-800 transition-colors hover:text-black dark:text-zinc-400 dark:hover:text-white";

export default function AuthForm({
  mode,
  brand = "cuadrao",
  allowModeSwitch = true,
  embedded = false,
  onModeChange,
  onSubmit,
  onConfirmEmailCode,
  onEmailConfirmed,
}: AuthFormProps) {
  const { t } = useTranslation();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authErrorKind, setAuthErrorKind] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [needsEmailConfirmation, setNeedsEmailConfirmation] = useState(false);
  const [confirmationCode, setConfirmationCode] = useState("");
  const [codeError, setCodeError] = useState<string | null>(null);
  const [isConfirming, setIsConfirming] = useState(false);
  const confirmationHeadingRef = useRef<HTMLHeadingElement>(null);
  const isSignup = mode === "signup";
  const acceptance = acceptanceLinks();

  useEffect(() => {
    setNeedsEmailConfirmation(false);
    setConfirmationCode("");
    setCodeError(null);
  }, [mode]);

  useEffect(() => {
    if (needsEmailConfirmation) {
      confirmationHeadingRef.current?.focus();
    }
  }, [needsEmailConfirmation]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAuthError(null);
    setAuthErrorKind(null);
    setIsSubmitting(true);
    try {
      const result = await onSubmit({
        mode,
        displayName: displayName.trim(),
        email: email.trim(),
        password,
      });
      setNeedsEmailConfirmation(
        Boolean(result && result.status === "email_confirmation_required"),
      );
    } catch (error) {
      setAuthErrorKind(authErrorCode(error));
      setAuthError(
        localizedAuthErrorMessage(error, (key, fallback) =>
          String(t(key, fallback)),
        ),
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleConfirmCode = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCodeError(null);
    setIsConfirming(true);
    try {
      const token = normalizeEmailOtp(confirmationCode);
      if (!token) throw new EmailOtpRejectedError();
      if (onConfirmEmailCode) {
        await onConfirmEmailCode({ email: email.trim(), code: token });
      } else {
        await verifyEmailOtp({
          email: email.trim(),
          token,
          type: "signup",
        });
      }
      await onEmailConfirmed?.();
    } catch (error) {
      setCodeError(
        localizedAuthErrorMessage(error, (key, fallback) =>
          String(t(key, fallback)),
        ),
      );
    } finally {
      setIsConfirming(false);
    }
  };

  return (
    <div
      data-auth-brand={brand}
      className={
        embedded
          ? "w-full"
          : "w-full rounded-[20px] border border-black/10 bg-white p-7 dark:border-white/10 dark:bg-[#151719]"
      }
    >
      {needsEmailConfirmation ? (
        <div
          data-testid="auth-check-email"
          role="status"
          aria-live="polite"
          className="w-full text-center"
        >
          <h2
            ref={confirmationHeadingRef}
            tabIndex={-1}
            className="font-display text-[24px] font-medium tracking-tight text-black outline-none dark:text-white"
          >
            {t("auth.signup.confirmation_title", "Check your email")}
          </h2>
          <p className="mt-3 text-[15px] leading-relaxed text-black/60 dark:text-white/60">
            {t(
              "auth.signup.confirmation_description",
              "Enter the code from the email, or open the confirmation link. Either one finishes creating your account.",
            )}
          </p>
          <form onSubmit={handleConfirmCode} className="mt-5 space-y-3 text-left">
            <label
              htmlFor="auth-confirmation-code"
              className="block px-1 text-[13px] tracking-[0.16px] text-black/55 dark:text-white/55"
            >
              {t("auth.signup.confirmation_code_label", "Confirmation code")}
            </label>
            <input
              id="auth-confirmation-code"
              data-testid="auth-confirmation-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={confirmationCode}
              onChange={(event) => setConfirmationCode(event.target.value)}
              required
              className="w-full rounded-[20px] border border-black/15 bg-transparent px-5 py-[14px] text-[16px] tracking-[0.16px] text-black transition-colors placeholder:text-black/40 focus:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black dark:border-white/20 dark:text-white dark:placeholder:text-white/40 dark:focus-visible:ring-white"
            />
            {codeError ? (
              <p role="alert" className={blockingErrorBannerClass}>
                {codeError}
              </p>
            ) : null}
            <button
              type="submit"
              disabled={isConfirming}
              className="font-display flex w-full items-center justify-center rounded-[9999px] bg-black px-[32px] py-[14px] text-[16px] font-medium text-white transition-opacity hover:opacity-85 focus:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black disabled:opacity-50 dark:bg-white dark:text-black dark:focus-visible:ring-white"
            >
              {isConfirming
                ? t("auth.signup.confirmation_loading", "Confirming...")
                : t("auth.signup.confirmation_submit", "Confirm")}
            </button>
          </form>
        </div>
      ) : (
        <>
          <form onSubmit={handleSubmit} className="space-y-3">
            {isSignup && (
              <input
                type="text"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder={t("auth.signup.name_placeholder", "Name")}
                autoComplete="name"
                className="w-full rounded-[20px] border border-black/15 bg-transparent px-5 py-[14px] text-[16px] tracking-[0.16px] text-black transition-colors placeholder:text-black/40 focus:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black dark:border-white/20 dark:text-white dark:placeholder:text-white/40 dark:focus-visible:ring-white"
              />
            )}

            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder={t("auth.login.email_placeholder", "Email address")}
              autoComplete="email"
              required
              autoFocus
              className="w-full rounded-[20px] border border-black/15 bg-transparent px-5 py-[14px] text-[16px] tracking-[0.16px] text-black transition-colors placeholder:text-black/40 focus:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black dark:border-white/20 dark:text-white dark:placeholder:text-white/40 dark:focus-visible:ring-white"
            />

            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder={t("auth.login.password_placeholder", "Password")}
                autoComplete={isSignup ? "new-password" : "current-password"}
                required
                minLength={isSignup ? 8 : undefined}
                aria-describedby={
                  isSignup ? "auth-signup-password-requirement" : undefined
                }
                className="w-full rounded-[20px] border border-black/15 bg-transparent px-5 py-[14px] pr-14 text-[16px] tracking-[0.16px] text-black transition-colors placeholder:text-black/40 focus:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black dark:border-white/20 dark:text-white dark:placeholder:text-white/40 dark:focus-visible:ring-white"
              />
              <button
                type="button"
                aria-label={
                  showPassword
                    ? t("auth.password.hide", "Hide password")
                    : t("auth.password.show", "Show password")
                }
                onClick={() => setShowPassword((visible) => !visible)}
                className="absolute right-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full text-black/45 transition-colors hover:bg-black/5 hover:text-black focus:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black dark:text-white/45 dark:hover:bg-white/10 dark:hover:text-white dark:focus-visible:ring-white"
              >
                {showPassword ? (
                  <EyeClosed className="h-5 w-5" />
                ) : (
                  <Eye className="h-5 w-5" />
                )}
              </button>
            </div>

            {isSignup && (
              <p
                id="auth-signup-password-requirement"
                className="-mt-1 px-1 text-[12px] tracking-[0.16px] text-black/55 dark:text-white/55"
              >
                {t(
                  "auth.signup.password_requirement",
                  "At least 8 characters.",
                )}
              </p>
            )}

            {!isSignup && (
              <a
                href="/auth/forgot-password"
                className="block px-1 text-right text-sm font-medium text-black/60 transition-opacity hover:opacity-75 dark:text-white/60"
              >
                {t("auth.recovery.forgot", "Forgot password?")}
              </a>
            )}

            {authError && (
              <p role="alert" className={blockingErrorBannerClass}>
                {authError}
              </p>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="font-display flex w-full items-center justify-center rounded-[9999px] bg-black px-[32px] py-[14px] text-[16px] font-medium text-white transition-opacity hover:opacity-85 focus:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black disabled:opacity-50 dark:bg-white dark:text-black dark:focus-visible:ring-white"
            >
              {isSubmitting ? (
                <>
                  <span
                    data-testid="auth-submit-spinner"
                    aria-hidden="true"
                    className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
                  />
                  {isSignup
                    ? t("auth.signup.loading", "Creating account...")
                    : t("auth.login.loading", "Signing in...")}
                </>
              ) : authErrorKind === "captcha_unavailable" ? (
                t("auth.errors.browser_check_retry", "Try again")
              ) : isSignup ? (
                t("auth.signup.submit", "Sign up")
              ) : (
                t("auth.login.submit", "Sign in")
              )}
            </button>
          </form>

          {allowModeSwitch && onModeChange && (
            <p className="mt-5 text-center text-[15px] tracking-wide text-gray-500 dark:text-gray-400">
              {isSignup
                ? t("landing.already_account", "Already have an account?")
                : t("auth.signup.new_account_cuadrao", "New to Cuadrao?")}{" "}
              <button
                type="button"
                className="font-medium text-black transition-opacity hover:opacity-80 dark:text-white"
                onClick={() => onModeChange(isSignup ? "login" : "signup")}
              >
                {isSignup
                  ? t("landing.sign_in", "Sign in")
                  : t("auth.signup.submit", "Sign up")}
              </button>
            </p>
          )}

          {acceptance ? (
            <p className="mt-5 w-full px-4 text-center text-[11px] tracking-tight text-zinc-500 md:text-[12px]">
              {isSignup
                ? t("landing.legal_prefix", "By signing up, you agree to our")
                : t(
                    "auth.legal.continuing_prefix",
                    "By continuing, you agree to our",
                  )}{" "}
              <a href={acceptance.terms} className={LEGAL_LINK_CLASS}>
                {t("landing.terms", "Terms")}
              </a>{" "}
              {t("common.and", "and")}{" "}
              <a href={acceptance.privacy} className={LEGAL_LINK_CLASS}>
                {t("landing.privacy", "Privacy Policy")}
              </a>
              .
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}
