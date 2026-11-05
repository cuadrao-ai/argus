"use client";

import { useTranslation } from "react-i18next";

import { useRetryAfterCountdown } from "@/lib/use-retry-after-countdown";

export function RecoveryEmailWait({ availableAtMs }: { availableAtMs: number }) {
  const { t } = useTranslation();
  const remaining = useRetryAfterCountdown(availableAtMs);
  return (
    <p role="status" data-testid="recovery-email-wait" className="text-sm text-[#2f5a49]">
      {t("auth.screen.email_wait", "Wait a minute before requesting another email.")}
      {" "}
      <span data-testid="recovery-email-countdown">{remaining}</span>
    </p>
  );
}
