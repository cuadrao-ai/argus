"use client";

import { useTranslation } from "react-i18next";

export function OfflineBanner({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      data-testid="offline-banner"
      className="rounded-[14px] bg-[#F7F5EE] px-4 py-3 text-[#2f5a49]"
    >
      <p className="font-sans text-base">{t("auth.screen.offline", "You are offline. Check your internet.")}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-3 inline-flex min-h-11 items-center justify-center rounded-full bg-[#2f5a49] px-5 font-sans text-base font-medium text-[#F7F5EE] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2f5a49] focus-visible:ring-offset-2 focus-visible:ring-offset-[#F7F5EE]"
      >
        {t("common.retry", "Retry")}
      </button>
    </div>
  );
}
