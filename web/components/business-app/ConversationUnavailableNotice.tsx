"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useTranslation } from "react-i18next";
import { CONVERSATION_UNAVAILABLE } from "@/lib/conversation-surface-guard";

/** A Personal conversation reached the Business build: one plain sentence and one link; nothing is requested again. */
export default function ConversationUnavailableNotice() {
  const { t } = useTranslation();
  const params = useSearchParams();
  if (params.get("notice") !== CONVERSATION_UNAVAILABLE) return null;
  return (
    <div role="status" data-testid="conversation-unavailable" className="fixed inset-x-0 top-0 z-50 flex justify-center px-4 pt-3">
      <p className="rounded-full border border-black/10 bg-white px-4 py-2 text-[14px] text-black shadow-sm dark:border-white/10 dark:bg-[#1f2225] dark:text-white">
        {t("business.notice.conversation_unavailable", "This conversation isn't available in Cuadrao Business.")}{" "}
        <Link href="/biz" className="font-medium underline underline-offset-4">{t("business.notice.go_business", "Go to Cuadrao Business")}</Link>
      </p>
    </div>
  );
}
