"use client";

import { useTranslation } from "react-i18next";

import { BrandedStatusScreen } from "@/components/status/BrandedStatusScreen";
import { useSessionEntry } from "@/components/status/useCuadraoEntryHref";

export function NotFoundScreen({ homeHref }: { homeHref?: string }) {
  const { t } = useTranslation();
  const session = useSessionEntry();
  return (
    <BrandedStatusScreen
      title={t("auth.screen.not_found_title", "We could not find this page.")}
      detail={t("auth.screen.not_found_detail", "The link may be old or copied wrong.")}
      actionLabel={t("auth.screen.go_to_cuadrao", "Go to Cuadrao")}
      actionHref={homeHref ?? session.homeHref}
    />
  );
}
