"use client";

import { useTranslation } from "react-i18next";

import { BrandedStatusScreen } from "@/components/status/BrandedStatusScreen";

export function RemovedMemberScreen({ onReturn }: { onReturn: () => void }) {
  const { t } = useTranslation();
  return (
    <BrandedStatusScreen
      testId="removed-member-screen"
      title={t("auth.screen.removed_title", "You do not have access to this business.")}
      actionLabel={t("auth.screen.go_to_businesses", "Go to my businesses")}
      onAction={onReturn}
    />
  );
}
