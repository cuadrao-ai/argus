"use client";

import { useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { BrandedStatusScreen } from "@/components/status/BrandedStatusScreen";
import { WEB_APP_NAME } from "@/lib/app-brand";

export function SessionRecoveryScreen({
  state,
  busy = false,
  onRetry,
  onContinue,
  continueDisabled = false,
}: {
  state: "missing" | "error" | "different-owner";
  busy?: boolean;
  onRetry: () => void;
  onContinue?: () => void;
  continueDisabled?: boolean;
}) {
  const { t } = useTranslation();
  const heading = useRef<HTMLHeadingElement>(null);
  const focusedState = useRef<typeof state | null>(null);
  const screens = {
    missing: {
      title: t("auth.session_recovery.missing_title"),
      detail: t("auth.session_recovery.missing_detail"),
      actionLabel: t("landing.sign_in"),
      actionHref: "/?auth=login",
      artwork: "/brand/session-door.png",
    },
    error: {
      title: t("auth.session_recovery.error_title"),
      actionLabel: t("account_security.retry"),
      onAction: onRetry,
    },
    "different-owner": {
      title: t("auth.session_recovery.different_owner_title"),
      detail: t("auth.session_recovery.different_owner_detail"),
      actionLabel: t("auth.screen.go_home"),
      onAction: onContinue,
      actionDisabled: continueDisabled || !onContinue,
    },
  };
  const screen = screens[state];
  const checking = busy && state !== "missing";

  useLayoutEffect(() => {
    document.title = WEB_APP_NAME;
  }, []);

  useLayoutEffect(() => {
    if (!checking && focusedState.current !== state && heading.current) {
      heading.current.focus({ preventScroll: true });
      focusedState.current = state;
    }
  }, [checking, state]);

  return (
    <BrandedStatusScreen
      {...screen}
      variant="recovery"
      headingRef={heading}
      busyLabel={checking ? t("auth.session_recovery.checking") : undefined}
      testId="session-recovery-screen"
    />
  );
}
