"use client";

import { EyeClosed } from "lucide-react";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import { FormField, PasswordField, useFieldChecks } from "@/components/ui/FormField";
import { PASSWORD_MIN_LENGTH } from "@/lib/password-strength";
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
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [request, setRequest] = useState<{ status: "idle" | "pending" } | { status: "failed"; code: string }>({ status: "idle" });
  const pending = useRef(false);
  const generation = useRef(0);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const id = useId();
  const isSubmitting = request.status === "pending";
  const authErrorKind = request.status === "failed" ? request.code : null;
  const errorMessage = authErrorKind === null ? null : AUTH_ERROR_MESSAGE_BY_CODE[authErrorKind] ?? GENERIC_AUTH_ERROR;
  const authError = errorMessage ? t(errorMessage.key, errorMessage.fallback) : null;
  const [needsEmailConfirmation, setNeedsEmailConfirmation] = useState(false);
  const [confirmationCode, setConfirmationCode] = useState("");
  const [codeError, setCodeError] = useState<string | null>(null);
  const [isConfirming, setIsConfirming] = useState(false);
  const confirmationHeadingRef = useRef<HTMLHeadingElement>(null);
  const isSignup = mode === "signup";
  const acceptance = acceptanceLinks();
  const labels = {
    email: t("auth.login.email_placeholder"),
    password: t("auth.login.password_placeholder"),
  };
  const messages = {
    emailRequired: t("auth.form.email_required"),
    emailInvalid: t("auth.form.email_invalid"),
    emailValid: t("auth.form.email_valid"),
    passwordRequired: t("auth.form.password_required"),
    passwordShort: t("auth.form.password_short", { min: PASSWORD_MIN_LENGTH }),
  };
  const checks = useFieldChecks({
    email: (values) => !values.email.trim() ? messages.emailRequired
      : emailRef.current?.validity.typeMismatch ? messages.emailInvalid : null,
    password: (values) => !values.password ? messages.passwordRequired
      : isSignup && values.password.length < PASSWORD_MIN_LENGTH ? messages.passwordShort : null,
  }, { email, password });
  const resetChecks = checks.reset;

  useEffect(() => {
    setNeedsEmailConfirmation(false);
    setConfirmationCode("");
    setCodeError(null);
    pending.current = false;
    setRequest({ status: "idle" });
    resetChecks();
    return () => { generation.current += 1; };
  }, [mode, resetChecks]);

  useEffect(() => {
    if (checks.attempt > 0) formRef.current?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus();
  }, [checks.attempt]);

  useEffect(() => {
    if (request.status === "failed") errorRef.current?.focus();
  }, [request]);

  useEffect(() => {
    if (needsEmailConfirmation) {
      confirmationHeadingRef.current?.focus();
    }
  }, [needsEmailConfirmation]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending.current) return;
    setRequest({ status: "idle" });
    if (!checks.submit()) return;
    pending.current = true;
    const current = generation.current;
    setRequest({ status: "pending" });
    try {
      const result = await onSubmit({
        mode,
        displayName: [firstName.trim(), lastName.trim()].filter(Boolean).join(" "),
        email: email.trim(),
        password,
      });
      if (current !== generation.current) return;
      setNeedsEmailConfirmation(Boolean(result && result.status === "email_confirmation_required"));
      setRequest({ status: "idle" });
    } catch (error) {
      if (current === generation.current) setRequest({ status: "failed", code: authErrorCode(error) });
    } finally {
      if (current === generation.current) pending.current = false;
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
              "Enter the code we sent to {{correo}}.",
              { correo: email.trim() },
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
          <h2 className="font-display mb-[21px] text-[24px] font-medium tracking-tight text-black dark:text-white">
            {t(`auth.${mode}.title`)}
          </h2>
          <form ref={formRef} onSubmit={handleSubmit} noValidate aria-busy={isSubmitting} className="space-y-3">
            {authError ? (
              <div data-auth-feedback="true">
                <p ref={errorRef} tabIndex={-1} role="alert" className={blockingErrorBannerClass}>{authError}</p>
              </div>
            ) : null}
            {isSignup && (
              <div role="group" aria-labelledby={`${id}-names-note`}>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <FormField id={`${id}-first-name`} label={t("auth.signup.first_name_placeholder")}
                  value={firstName} onChange={(event) => setFirstName(event.target.value)}
                  autoComplete="given-name" reserveMessages={[]} readOnly={isSubmitting} />
                <FormField id={`${id}-last-name`} label={t("auth.signup.last_name_placeholder")}
                  value={lastName} onChange={(event) => setLastName(event.target.value)}
                  autoComplete="family-name" reserveMessages={[]} readOnly={isSubmitting} />
                </div>
                <p id={`${id}-names-note`} className="mt-1.5 text-[12px]">{t("auth.form.names_optional")}</p>
              </div>
            )}
            <FormField ref={emailRef} id={`${id}-email`} type="email" label={labels.email}
              value={email} onChange={(event) => { setEmail(event.target.value); if (request.status === "failed") setRequest({ status: "idle" }); }}
              onBlur={() => checks.blur("email")} error={checks.errorOf("email")}
              success={checks.isValid("email") ? messages.emailValid : undefined}
              reserveMessages={[messages.emailRequired, messages.emailInvalid, messages.emailValid]}
              autoComplete="email" autoCapitalize="none" spellCheck={false} required readOnly={isSubmitting} />
            <PasswordField key={mode} id={`${id}-password`} label={labels.password}
              value={password} onChange={(event) => { setPassword(event.target.value); if (request.status === "failed") setRequest({ status: "idle" }); }}
              onBlur={() => checks.blur("password")} error={checks.errorOf("password")}
              reserveMessages={isSignup ? [messages.passwordRequired, messages.passwordShort] : [messages.passwordRequired]}
              advice={t("auth.form.password_advice")} coaching="on-focus"
              hideIcon={<EyeClosed className="h-5 w-5" aria-hidden="true" />}
              autoComplete={isSignup ? "new-password" : "current-password"}
              required readOnly={isSubmitting} minLength={isSignup ? PASSWORD_MIN_LENGTH : undefined} />

            {!isSignup && (
              <a
                href="/auth/forgot-password"
                className="block px-1 text-right text-sm font-medium text-black/60 transition-opacity hover:opacity-75 dark:text-white/60"
              >
                {t("auth.recovery.forgot", "Forgot password?")}
              </a>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="font-display flex w-full items-center justify-center rounded-[9999px] bg-black px-[32px] py-[14px] text-[16px] font-medium text-white transition-opacity hover:opacity-85 focus:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black disabled:cursor-wait disabled:opacity-100 dark:bg-white dark:text-black dark:focus-visible:ring-white"
            >
              {isSubmitting ? (
                <>
                  <span
                    data-testid="auth-submit-spinner"
                    aria-hidden="true"
                    className="mr-2 h-4 w-4 animate-spin motion-reduce:animate-none rounded-full border-2 border-current border-t-transparent"
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
                t("auth.login.submit", "Continue")
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
                disabled={isSubmitting}
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
