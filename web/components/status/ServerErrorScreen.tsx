"use client";

import { useTranslation } from "react-i18next";

import { BrandedStatusScreen } from "@/components/status/BrandedStatusScreen";
import { useSessionEntry } from "@/components/status/useCuadraoEntryHref";
import { CUADRAO_ADMIN_EMAIL } from "@/lib/failure-screen";

export function ServerErrorScreen({
  onRetry,
  reference,
  homeHref,
}: {
  onRetry: () => void;
  reference: string;
  homeHref?: string;
}) {
  const { t } = useTranslation();
  const session = useSessionEntry();
  return (
    <BrandedStatusScreen
      testId="server-error-screen"
      title={t("auth.screen.server_title", "Something went wrong on our side.")}
      actionLabel={t("auth.screen.try_again", "Try again")}
      onAction={onRetry}
      secondaryLabel={t("auth.screen.go_home", "Go to Home")}
      secondaryHref={homeHref ?? session.homeHref}
      reference={reference}
      contactEmail={CUADRAO_ADMIN_EMAIL}
    />
  );
}
