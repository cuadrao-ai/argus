"use client";

import Link from "next/link";
import { rememberRecoveryEmail } from "./recovery-email";

import { AlertCircle, Check, EyeClosed, LoaderCircle } from "lucide-react";
import Image from "next/image";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import { FormField, PasswordField, useFieldChecks } from "@/components/ui/FormField";
import { fieldLabelClass } from "@/components/ui/form-field";
import { PASSWORD_MIN_LENGTH } from "@/lib/password-strength";
import { Trans, useTranslation } from "react-i18next";
import { acceptanceLinks } from "@/lib/cuadrao-legal-links";
import {
  EmailOtpRejectedError,
  EmailOtpError,
  resendSignupEmail,
  type EmailResendAcceptance,
  normalizeEmailOtp,
  verifyEmailOtp,
} from "@/lib/email-otp";
import { blockingErrorBannerClass } from "@/lib/failure-treatment";

const CONFIRMATION_CODE_LENGTH = 8;

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
  emailFirst?: boolean;
  onModeChange?: (mode: AuthFormMode) => void;
  onSubmit: (
    submission: AuthFormSubmission,
  ) => Promise<AuthFormSubmissionResult | void>;
  onConfirmEmailCode?: (input: { email: string; code: string }) => Promise<void>;
  onEmailConfirmed?: () => void | Promise<void>;
  onResendEmailCode?: (input: { email: string }) => Promise<EmailResendAcceptance | void>;
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
  emailFirst = false,
  onModeChange,
  onSubmit,
  onConfirmEmailCode,
  onEmailConfirmed,
  onResendEmailCode,
}: AuthFormProps) {
  const { t } = useTranslation();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [entry, setEntry] = useState<{ mode: AuthFormMode; step: "identity" | "password" }>({ mode, step: "identity" });
  const entryStep = entry.mode === mode ? entry.step : "identity";
  const isIdentityStep = emailFirst && entryStep === "identity";
  const cardRef = useRef<HTMLDivElement>(null);
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
  const [codeErrorKind, setCodeErrorKind] = useState<string | null>(null);
  const [confirmationStatus, setConfirmationStatus] = useState<"editing" | "verifying" | "verified">("editing");
  const [activeSlot, setActiveSlot] = useState(0);
  const [rejectionCount, setRejectionCount] = useState(0);
  const confirmationInputRef = useRef<HTMLInputElement>(null);
  const confirming = useRef(false);
  const isConfirming = confirmationStatus === "verifying";
  const isVerified = confirmationStatus === "verified";
  const codeErrorMessage = codeErrorKind !== null ? AUTH_ERROR_MESSAGE_BY_CODE[codeErrorKind] ?? GENERIC_AUTH_ERROR : null;
  const codeError = codeErrorKind === "incomplete"
    ? t("auth.signup.confirmation_code_incomplete", { count: CONFIRMATION_CODE_LENGTH })
    : codeErrorKind === "malformed" ? t("auth.signup.confirmation_code_malformed", { count: CONFIRMATION_CODE_LENGTH })
    : codeErrorKind === "otp_transient" ? t("auth.signup.confirmation_temporary_error")
    : codeErrorKind === "otp_rejected" || codeErrorKind === "otp_expired" ? t("auth.signup.confirmation_code_rejected")
    : codeErrorKind === "too_many_requests" ? t("auth.signup.confirmation_rate_limited")
    : codeErrorMessage ? t(codeErrorMessage.key, codeErrorMessage.fallback) : null;
  const [resend, setResend] = useState<{ status: "idle" | "pending" | "sent" } | { status: "failed"; code: string }>({ status: "idle" });
  const isResending = resend.status === "pending";
  const [resendAvailableAt, setResendAvailableAt] = useState(0);
  const [resendSeconds, setResendSeconds] = useState(30);
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
    password: (values) => isIdentityStep ? null : !values.password ? messages.passwordRequired
      : isSignup && values.password.length < PASSWORD_MIN_LENGTH ? messages.passwordShort : null,
  }, { email, password });
  const resetChecks = checks.reset;

  useEffect(() => {
    if (emailFirst) {
      setPassword("");
      setEntry({ mode, step: "identity" });
    }
    setNeedsEmailConfirmation(false);
    setConfirmationCode("");
    setCodeErrorKind(null);
    setConfirmationStatus("editing");
    setRejectionCount(0);
    setResend({ status: "idle" });
    setResendAvailableAt(0);
    setResendSeconds(30);
    setActiveSlot(0);
    confirming.current = false;
    pending.current = false;
    setRequest({ status: "idle" });
    resetChecks();
    return () => { generation.current += 1; };
  }, [mode, resetChecks, emailFirst]);

  useEffect(() => {
    if (emailFirst && entry.mode === mode && entryStep === "password") {
      const frame = requestAnimationFrame(() => {
        formRef.current?.querySelector<HTMLInputElement>('input[autocomplete$="password"]')?.focus();
      });
      return () => cancelAnimationFrame(frame);
    }
  }, [emailFirst, entry, entryStep, mode]);

  useEffect(() => {
    if (checks.attempt > 0) formRef.current?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus();
  }, [checks.attempt]);

  useEffect(() => {
    if (request.status === "failed") errorRef.current?.focus();
  }, [request]);

  useEffect(() => {
    if (needsEmailConfirmation) {
      confirmationHeadingRef.current?.focus();
      setResendAvailableAt(Date.now() + 30_000);
    }
  }, [needsEmailConfirmation]);

  useEffect(() => {
    if (!needsEmailConfirmation) return;
    const update = () => setResendSeconds(Math.max(0, Math.ceil((resendAvailableAt - Date.now()) / 1000)));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [needsEmailConfirmation, resendAvailableAt]);

  const resendFeedback = resend.status === "pending" ? t("auth.signup.confirmation_resend_pending")
    : resend.status === "sent" ? t("auth.signup.confirmation_resend_sent")
    : resend.status === "failed" ? resend.code === "too_many_requests" ? t("auth.signup.confirmation_rate_limited")
    : t("auth.signup.confirmation_resend_failed") : null;

  const updateConfirmationCode = (value: string) => {
    const digits = value.replace(/\s+/g, "");
    if (!/^[0-9]*$/.test(digits) || digits.length > CONFIRMATION_CODE_LENGTH) {
      setCodeErrorKind("malformed");
      return;
    }
    setConfirmationCode(digits);
    setActiveSlot(Math.min(digits.length, CONFIRMATION_CODE_LENGTH - 1));
    setCodeErrorKind(null);
  };

  const handleResendCode = async () => {
    if (confirming.current || isVerified || Date.now() < resendAvailableAt) return;
    confirming.current = true;
    const current = generation.current;
    setResend({ status: "pending" });
    setCodeErrorKind(null);
    try {
      const accepted = await (onResendEmailCode ? onResendEmailCode({ email: email.trim() }) : resendSignupEmail({ email: email.trim() }));
      if (current !== generation.current) return;
      setResend({ status: "sent" });
      const seconds = accepted?.retryAfterSeconds ?? 30;
      setResendAvailableAt(Date.now() + seconds * 1000);
      setResendSeconds(seconds);
    } catch (error) {
      if (current !== generation.current) return;
      setResend({ status: "failed", code: authErrorCode(error) });
      if (error instanceof EmailOtpError && error.code === "too_many_requests") {
        const seconds = error.retryAfterSeconds ?? 30;
        setResendAvailableAt(Date.now() + seconds * 1000);
        setResendSeconds(seconds);
      }
    } finally {
      if (current === generation.current) confirming.current = false;
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending.current) return;
    setRequest({ status: "idle" });
    if (!checks.submit()) return;
    if (isIdentityStep) {
      resetChecks();
      setEntry({ mode, step: "password" });
      return;
    }
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
    if (confirming.current || (isVerified && !codeErrorKind)) return;
    if (!isVerified && (codeErrorKind === "malformed" || confirmationCode.length !== CONFIRMATION_CODE_LENGTH)) {
      setCodeErrorKind(codeErrorKind === "malformed" ? "malformed" : "incomplete");
      confirmationInputRef.current?.focus();
      return;
    }
    confirming.current = true;
    const current = generation.current;
    setCodeErrorKind(null);
    setResend({ status: "idle" });
    if (!isVerified) {
      setConfirmationStatus("verifying");
      try {
        const token = normalizeEmailOtp(confirmationCode);
        if (!token) throw new EmailOtpRejectedError();
        if (onConfirmEmailCode) {
          await onConfirmEmailCode({ email: email.trim(), code: token });
        } else {
          await verifyEmailOtp({ email: email.trim(), token, type: "signup" });
        }
        if (current !== generation.current) return;
        setConfirmationStatus("verified");
      } catch (error) {
        if (current !== generation.current) return;
        setCodeErrorKind(authErrorCode(error) || "generic");
        setConfirmationStatus("editing");
        if (["otp_rejected", "otp_expired"].includes(authErrorCode(error))) {
          setConfirmationCode("");
          setActiveSlot(0);
          setRejectionCount((count) => count + 1);
        }
        confirming.current = false;
        requestAnimationFrame(() => {
          if (current === generation.current) confirmationInputRef.current?.focus();
        });
        return;
      }
    }
    try {
      await onEmailConfirmed?.();
    } catch (error) {
      if (current === generation.current) setCodeErrorKind(authErrorCode(error) || "generic");
    } finally {
      if (current === generation.current) confirming.current = false;
    }
  };

  return (
    <div
      ref={cardRef}
      data-auth-entry-step={emailFirst ? entryStep : undefined}
      data-auth-brand={brand}
      data-auth-step={needsEmailConfirmation ? "confirmation" : undefined}
      className={
        needsEmailConfirmation
          ? "w-full px-1 py-7 min-[80rem]:pt-[55px]"
          : embedded
          ? "w-full"
          : "w-full rounded-[20px] border border-black/10 bg-white p-7 dark:border-white/10 dark:bg-[#151719]"
      }
    >
      {needsEmailConfirmation ? (
        <div data-testid="auth-check-email" className="w-full text-center">
          <div
            data-confirmation-illustration="true"
            aria-hidden="true"
            className="mx-auto mb-[21px] h-[112px] w-[168px]"
          >
            <Image src="/images/auth/confirmation-envelope.png" alt="" width={1536} height={1024} sizes="168px" className="h-full w-full object-contain" />
          </div>
          <h2
            ref={confirmationHeadingRef}
            tabIndex={-1}
            className="font-display text-balance text-[28px] font-medium leading-[1.2] tracking-tight text-black outline-none dark:text-white min-[80rem]:text-[40px]"
          >
            {t("auth.signup.confirmation_title", "Check your email")}
          </h2>
          <p className="mx-auto mt-[13px] max-w-md text-[16px] leading-relaxed text-black/60 dark:text-white/60">
            <Trans
              i18nKey="auth.signup.confirmation_description"
              values={{ correo: email.trim() }}
              components={{ email: <strong className="font-medium [overflow-wrap:anywhere]" /> }}
            />
          </p>
          <form onSubmit={handleConfirmCode} aria-busy={isConfirming || isResending} className="mx-auto mt-[34px] max-w-[400px] space-y-2 text-left">
            <div>
              <label htmlFor="auth-confirmation-code" className={`${fieldLabelClass} text-center`}>
                {t("auth.signup.confirmation_code_label")}
              </label>
              <div data-otp-control data-otp-status={confirmationStatus} data-otp-error={Boolean(codeError && !isVerified)}>
                <input
                  ref={confirmationInputRef}
                  id="auth-confirmation-code"
                  data-testid="auth-confirmation-code"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  aria-required="true"
                  spellCheck={false}
                  autoCapitalize="off"
                  value={confirmationCode}
                  readOnly={isConfirming || isResending || isVerified}
                  aria-invalid={codeError && !isVerified ? true : undefined}
                  aria-describedby="auth-confirmation-code-note"
                  onChange={(event) => updateConfirmationCode(event.target.value)}
                  onSelect={(event) => setActiveSlot(Math.min(event.currentTarget.selectionStart ?? confirmationCode.length, CONFIRMATION_CODE_LENGTH - 1))}
                  onBlur={() => {
                    if (codeErrorKind !== "malformed" && confirmationCode && confirmationCode.length !== CONFIRMATION_CODE_LENGTH) setCodeErrorKind("incomplete");
                  }}
                  onPaste={(event) => {
                    if (isConfirming || isResending || isVerified) return;
                    event.preventDefault();
                    updateConfirmationCode(event.clipboardData.getData("text"));
                  }}
                />
                <div key={rejectionCount} data-otp-slots data-otp-rejected={rejectionCount > 0} aria-hidden="true">
                  {Array.from({ length: CONFIRMATION_CODE_LENGTH }, (_, index) => (
                    <span
                      key={index}
                      data-otp-slot={index}
                      data-active={index === activeSlot}
                      onPointerDown={(event) => {
                        event.preventDefault();
                        if (isConfirming || isResending || isVerified) return;
                        const input = confirmationInputRef.current;
                        const position = Math.min(index, confirmationCode.length);
                        input?.focus();
                        input?.setSelectionRange(position, position < confirmationCode.length ? position + 1 : position);
                        setActiveSlot(Math.min(position, CONFIRMATION_CODE_LENGTH - 1));
                      }}
                    >{confirmationCode[index] ?? ""}</span>
                  ))}
                </div>
              </div>
              <div className="mt-1.5 grid text-[14px] leading-[22px]">
                {["auth.signup.confirmation_code_rejected", "auth.signup.confirmation_code_incomplete", "auth.errors.generic"].map((key) => (
                  <p key={key} aria-hidden="true" className="invisible col-start-1 row-start-1 flex gap-1.5">
                    <span className="h-4 w-4 shrink-0" />{t(key, { count: CONFIRMATION_CODE_LENGTH })}
                  </p>
                ))}
                <p id="auth-confirmation-code-note" aria-live="polite" className={`col-start-1 row-start-1 flex min-h-[22px] gap-1.5 ${(codeError || resend.status === "failed") ? "text-[#9e2f39]! dark:text-[#ec9aa0]!" : "text-[#2f5a49]! dark:text-[#8fcbb0]!"}`}>
                  {codeError ? <AlertCircle aria-hidden="true" className="mt-[3px] h-4 w-4 shrink-0" /> : isVerified ? <Check aria-hidden="true" className="mt-[3px] h-4 w-4 shrink-0" /> : null}
                  {codeError || resendFeedback || (isVerified ? t("auth.signup.confirmation_verified") : "")}
                </p>
              </div>
            </div>
            <button
              type="submit"
              disabled={isConfirming || isResending || (isVerified && !codeErrorKind)}
              className="font-display flex w-full items-center justify-center rounded-[9999px] bg-black px-[32px] py-[14px] text-[16px] font-medium text-white transition-opacity hover:opacity-85 focus:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black disabled:opacity-50 dark:bg-white dark:text-black dark:focus-visible:ring-white"
            >
              {isConfirming ? <LoaderCircle aria-hidden="true" className="mr-2 h-4 w-4 animate-spin motion-reduce:animate-none" /> : null}
              {isConfirming
                ? t("auth.signup.confirmation_loading", "Confirming...")
                : isVerified && codeErrorKind ? t("auth.login.submit")
                : isVerified ? t("auth.signup.confirmation_verified")
                : t("auth.signup.confirmation_submit", "Confirm")}
            </button>
          </form>
          <p className="mx-auto mt-[21px] max-w-[400px] text-[14px] leading-relaxed text-black/60 dark:text-white/60">
            {t("auth.signup.confirmation_help")}
          </p>
          <div className="mx-auto mt-3 max-w-[400px] text-center text-[14px]">
            <button type="button" disabled={resendSeconds > 0 || isConfirming || isResending || isVerified}
              className="min-h-11 rounded-item px-3 underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] disabled:cursor-not-allowed disabled:no-underline"
              onClick={() => void handleResendCode()}>
              {resendSeconds > 0 ? t("auth.signup.confirmation_resend_wait", { seconds: resendSeconds }) : t("auth.signup.confirmation_resend")}
            </button>
          </div>
          <div data-testid="auth-check-email-exits" className="mx-auto mt-3 flex max-w-[400px] flex-col items-center gap-1 text-[14px] text-black/60 dark:text-white/60">
            {allowModeSwitch && onModeChange ? (
              <p>
                {t("landing.already_account")}{" "}
                <button type="button" disabled={isConfirming}
                  className="min-h-11 rounded-item px-1 font-medium text-black underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] dark:text-white"
                  onClick={() => {
                    onModeChange("login");
                    if (emailFirst) requestAnimationFrame(() => cardRef.current?.querySelector("h2")?.focus());
                  }}>
                  {t("landing.sign_in")}
                </button>
              </p>
            ) : null}
            <Link href="/auth/forgot-password" onClick={() => rememberRecoveryEmail(email)}
              className="flex min-h-11 items-center rounded-item px-3 font-medium text-black underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] dark:text-white">
              {t("auth.recovery.forgot")}
            </Link>
          </div>
        </div>
      ) : (
        <div data-auth-entry-content={emailFirst ? "true" : undefined}>
          <h2 tabIndex={-1} className="outline-none font-display mb-[21px] text-[24px] font-medium tracking-tight text-black dark:text-white">
            {t(`auth.${mode}.title`)}
          </h2>
          <form ref={formRef} onSubmit={handleSubmit} noValidate aria-busy={isSubmitting} className="space-y-3">
            {authError ? (
              <div data-auth-feedback="true">
                <p ref={errorRef} tabIndex={-1} role="alert" className={blockingErrorBannerClass}>{authError}</p>
              </div>
            ) : null}
            {(emailFirst || isSignup) && (
              <div data-auth-collapse={emailFirst ? "true" : undefined} data-open={isSignup && (!emailFirst || isIdentityStep)}
                aria-hidden={emailFirst && (!isSignup || !isIdentityStep) ? true : undefined}
                inert={emailFirst && (!isSignup || !isIdentityStep)}>
              <div><div role="group" aria-labelledby={`${id}-names-note`}>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <FormField id={`${id}-first-name`} label={t("auth.signup.first_name_placeholder")}
                  placeholder={emailFirst ? t("auth.form.first_name_hint") : undefined}
                  value={firstName} onChange={(event) => setFirstName(event.target.value)}
                  autoComplete="given-name" reserveMessages={[]} readOnly={isSubmitting} />
                <FormField id={`${id}-last-name`} label={t("auth.signup.last_name_placeholder")}
                  placeholder={emailFirst ? t("auth.form.last_name_hint") : undefined}
                  value={lastName} onChange={(event) => setLastName(event.target.value)}
                  autoComplete="family-name" reserveMessages={[]} readOnly={isSubmitting} />
                </div>
                <p id={`${id}-names-note`} className="mt-1.5 text-[12px]">{t("auth.form.names_optional")}</p>
              </div></div></div>
            )}
            {emailFirst && (
              <div data-auth-collapse="true" data-open={!isIdentityStep} aria-hidden={isIdentityStep || undefined} inert={isIdentityStep}>
              <div><div className="mb-2 flex items-center justify-between gap-3 rounded-lg border border-current/15 px-3 py-2">
                <div className="min-w-0">
                  <p className="text-[12px] opacity-70">{labels.email}</p>
                  <p className="break-all text-[15px]">{email}</p>
                  <input type="hidden" name="username" autoComplete="username" value={email} />
                </div>
                <button type="button" disabled={isSubmitting} className="min-h-11 shrink-0 rounded px-2 text-sm underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2"
                  onClick={() => {
                    setPassword(""); resetChecks(); setRequest({ status: "idle" }); setEntry({ mode, step: "identity" });
                    requestAnimationFrame(() => emailRef.current?.focus());
                  }}>{t("auth.form.edit_email")}</button>
              </div></div></div>
            )}
            <div data-auth-collapse={emailFirst ? "true" : undefined} data-open={!emailFirst || isIdentityStep}
              aria-hidden={emailFirst && !isIdentityStep ? true : undefined} inert={emailFirst && !isIdentityStep}>
              <div><FormField ref={emailRef} id={`${id}-email`} type="email" label={labels.email}
              placeholder={emailFirst ? t("auth.form.email_hint") : undefined}
              value={email} onChange={(event) => { setEmail(event.target.value); if (request.status === "failed") setRequest({ status: "idle" }); }}
              onBlur={() => checks.blur("email")} error={checks.errorOf("email")}
              success={checks.isValid("email") ? messages.emailValid : undefined}
              reserveMessages={[messages.emailRequired, messages.emailInvalid, messages.emailValid]}
              autoComplete="email" autoCapitalize="none" spellCheck={false} required readOnly={isSubmitting} /></div>
            </div>
            <div data-auth-collapse={emailFirst ? "true" : undefined} data-open={!isIdentityStep}
              aria-hidden={isIdentityStep || undefined} inert={isIdentityStep}>
              <div><PasswordField key={mode} id={`${id}-password`} label={labels.password}
              placeholder={emailFirst ? t("auth.form.password_hint") : undefined}
              value={password} onChange={(event) => { setPassword(event.target.value); if (request.status === "failed") setRequest({ status: "idle" }); }}
              onBlur={() => checks.blur("password")} error={checks.errorOf("password")}
              reserveMessages={isSignup ? [messages.passwordRequired, messages.passwordShort] : [messages.passwordRequired]}
              advice={t("auth.form.password_advice")} coaching="on-focus"
              hideIcon={<EyeClosed className="h-5 w-5" aria-hidden="true" />}
              autoComplete={isSignup ? "new-password" : "current-password"}
              required readOnly={isSubmitting} minLength={isSignup ? PASSWORD_MIN_LENGTH : undefined} />

            {!isSignup && (
              <Link
                href="/auth/forgot-password"
                onClick={() => rememberRecoveryEmail(email)}
                className="mt-3 block px-1 text-right text-sm font-medium text-black/60 transition-opacity hover:opacity-75 dark:text-white/60"
              >
                {t("auth.recovery.forgot", "Forgot password?")}
              </Link>
            )}
              </div>
            </div>

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
              ) : isIdentityStep ? (
                t("auth.login.submit")
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
                onClick={() => {
                  onModeChange(isSignup ? "login" : "signup");
                  if (emailFirst) requestAnimationFrame(() => cardRef.current?.querySelector("h2")?.focus());
                }}
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
        </div>
      )}
    </div>
  );
}
