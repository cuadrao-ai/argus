"use client";

import { withViewportPortal } from "@/components/ui/withViewportPortal";

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import AuthForm, {
  type AuthFormMode,
  type AuthFormSubmission,
  type AuthFormSubmissionResult,
} from "@/components/auth/AuthForm";
import RequestAccess from "@/components/auth/RequestAccess";
import {
  guestConversionBenefitKey,
  type GuestConversionMode,
  type GuestConversionReason,
} from "@/lib/guest-conversion";
import { formatAllowancePeriodEnd } from "@/lib/usage-allowance";

type GuestConversionModalProps = {
  isOpen: boolean;
  reason: GuestConversionReason;
  initialMode: GuestConversionMode;
  publicAccountAccessEnabled: boolean;
  resetAt?: string | null;
  resetKind?: "daily" | "workspace";
  locale?: "en-US" | "es-419";
  onClose: () => void;
  onAuthenticate: (
    submission: AuthFormSubmission,
  ) => Promise<AuthFormSubmissionResult | void>;
  onEmailConfirmed?: () => void | Promise<void>;
};

export function GuestConversionModalSurface({
  isOpen,
  reason,
  initialMode,
  publicAccountAccessEnabled,
  resetAt = null,
  resetKind = "daily",
  locale = "en-US",
  onClose,
  onAuthenticate,
  onEmailConfirmed,
}: GuestConversionModalProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<AuthFormMode | "request">(
    publicAccountAccessEnabled ? initialMode : "request",
  );
  const dialogRef = useRef<HTMLDivElement>(null);
  // This modal is mounted fresh for each open. Capture the trigger during
  // render, before a child `autoFocus` can move focus inside the dialog.
  const restoreFocusRef = useRef<HTMLElement | null>(
    typeof document !== "undefined" &&
      document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null,
  );

  useEffect(() => {
    if (!isOpen) return;
    const restoreFocusTarget = restoreFocusRef.current;
    setMode(publicAccountAccessEnabled ? initialMode : "request");
    const dialog = dialogRef.current;
    const focusable = dialog?.querySelector<HTMLElement>(
      'input, button, a[href], [tabindex]:not([tabindex="-1"])',
    );
    focusable?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      const elements = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'input, button, a[href], [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => !element.hasAttribute("disabled"));
      if (elements.length === 0) return;
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      restoreFocusTarget?.focus();
    };
  }, [initialMode, isOpen, onClose, publicAccountAccessEnabled]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center p-4">
      <button
        tabIndex={-1}
        type="button"
        aria-label={t("common.cancel", "Cancel")}
        className="absolute inset-0 bg-black/25 backdrop-blur-sm dark:bg-black/65"
        onClick={onClose}
      />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="guest-conversion-title"
        className="relative w-full max-w-[440px] rounded-[20px] border border-black/10 bg-[#f9f9f9] p-6 dark:border-white/10 dark:bg-[#1c1f24] sm:p-8"
      >
        <button
          type="button"
          onClick={onClose}
          aria-label={t("common.cancel", "Cancel")}
          className="absolute right-4 top-4 flex h-11 w-11 items-center justify-center rounded-full text-black/45 transition-colors hover:bg-black/5 hover:text-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/25 dark:text-white/45 dark:hover:bg-white/8 dark:hover:text-white dark:focus-visible:ring-white/25"
        >
          <X className="h-5 w-5" />
        </button>
        <p className="mb-2 pr-12 font-display text-[12px] font-semibold uppercase tracking-[0.14em] text-black/45 dark:text-white/45">
          {t("guest.conversion.eyebrow", "Keep going with Cuadrao")}
        </p>
        {reason === "simulation_limit" && resetAt ? (
          <p className="mb-5 pr-12 text-[14px] leading-relaxed text-black/60 dark:text-white/60">
            {t(
              resetKind === "daily"
                ? publicAccountAccessEnabled
                  ? "guest.conversion.simulation_limit_reset"
                  : "guest.conversion.simulation_limit_request_access"
                : publicAccountAccessEnabled
                  ? "guest.conversion.simulation_workspace_limit_reset"
                  : "guest.conversion.simulation_workspace_limit_request_access",
              {
              date: formatAllowancePeriodEnd(resetAt, locale),
              },
            )}
          </p>
        ) : null}
        {mode === "request" ? (
          <RequestAccess
            headingId="guest-conversion-title"
            embedded
            onShowSignup={() => setMode("signup")}
            onShowLogin={() => setMode("login")}
          />
        ) : (
          <>
            <div className="mb-6 pr-12">
              <h2
                id="guest-conversion-title"
                className="font-display text-[24px] font-semibold tracking-tight text-black dark:text-white"
              >
                {t(
                  mode === "signup"
                    ? "guest.conversion.create_title"
                    : "guest.conversion.sign_in_title",
                  mode === "signup" ? "Create your account" : "Sign in",
                )}
              </h2>
              <p className="mt-2 text-[14px] leading-relaxed text-black/55 dark:text-white/55">
                {t(guestConversionBenefitKey(reason, mode))}
              </p>
            </div>
            <AuthForm
              mode={mode}
              allowModeSwitch={publicAccountAccessEnabled}
              embedded
              onModeChange={setMode}
              onSubmit={onAuthenticate}
              onEmailConfirmed={onEmailConfirmed}
            />
          </>
        )}
      </div>
    </div>
  );
}

export default withViewportPortal(GuestConversionModalSurface);
