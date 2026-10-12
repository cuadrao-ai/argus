"use client";

import { MessageSquareWarning } from "lucide-react";
import { CuadraoMark } from "@/components/CuadraoMark";
import { useTranslation } from "react-i18next";
import { panelFailureIconClass } from "@/lib/failure-treatment";

type ConversationRetrievalStateProps =
  | Readonly<{
      state: "loading";
      onRetry?: never;
    }>
  | Readonly<{
      state: "error";
      onRetry: () => void;
    }>;

export function ConversationRetrievalAnnouncement() {
  const { t } = useTranslation();

  return (
    <span
      data-testid="conversation-retrieval-announcement"
      className="sr-only"
      role="status"
      aria-live="polite"
    >
      {t("chat.opening_conversation", "Opening conversation…")}
    </span>
  );
}

export default function ConversationRetrievalState(
  props: ConversationRetrievalStateProps,
) {
  const { t } = useTranslation();

  if (props.state === "error") {
    return (
      <div
        data-testid="conversation-retrieval-error"
        role="alert"
        className="flex min-h-[45vh] flex-col items-center justify-center gap-4 px-6 text-center"
      >
        <MessageSquareWarning className={panelFailureIconClass} aria-hidden="true" />
        <p className="text-[14px] text-black/55 dark:text-white/55">
          {t(
            "chat.error_open_conversation",
            "Couldn’t open this conversation.",
          )}
        </p>
        <button
          type="button"
          onClick={props.onRetry}
          className="min-h-11 rounded-full border border-black/10 bg-white px-5 text-[14px] font-medium text-black transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/35 focus-visible:ring-offset-2 dark:border-white/10 dark:bg-[#1d2023] dark:text-white dark:hover:bg-white/6 dark:focus-visible:ring-white/45 dark:focus-visible:ring-offset-[#141517]"
        >
          {t("common.retry", "Retry")}
        </button>
      </div>
    );
  }

  return (
    <div
      data-testid="conversation-retrieval-state"
      aria-hidden="true"
      className="flex min-h-[45vh] flex-col items-center justify-center gap-4 px-6 text-center"
    >
      <CuadraoMark size={28} className="h-7 w-7 animate-pulse motion-reduce:animate-none" />
      <p className="text-[13px] text-black/45 dark:text-white/45">
        {t("chat.opening_conversation", "Opening conversation…")}
      </p>
    </div>
  );
}
