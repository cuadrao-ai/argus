"use client";

import { MessageSquareWarning } from "lucide-react";
import { CuadraoMark } from "@/components/CuadraoMark";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { panelFailureIconClass } from "@/lib/failure-treatment";
import { COLD_TRANSCRIPT_RETRIEVAL_DELAY_MS } from "@/lib/chat-conversation-view-helpers";

type ConversationRetrievalStateProps =
  | Readonly<{
      state: "loading";
      onRetry?: never;
    }>
  | Readonly<{
      state: "error";
      onRetry: () => void;
    }>;

export function ConversationRetrievalAnnouncement({ business = false, initial = false }: { business?: boolean; initial?: boolean }) {
  const { t, i18n } = useTranslation();
  const spanishBusiness = business && (i18n.resolvedLanguage ?? i18n.language).startsWith("es");

  return (
    <span
      data-testid="conversation-retrieval-announcement"
      className="sr-only"
      role="status"
      aria-live="polite"
    >
      {spanishBusiness ? "Cargando Cuadrao" : initial ? t("guest.entry.loading", "Opening Argus") : t("chat.opening_conversation", "Opening conversation…")}
    </span>
  );
}

export function InitialConversationRetrievalState({ business = false }: { business?: boolean }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(true), COLD_TRANSCRIPT_RETRIEVAL_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, []);
  if (!visible) return null;
  return <>
    <ConversationRetrievalAnnouncement business={business} initial />
    <ConversationRetrievalState state="loading" business={business} />
  </>;
}

export default function ConversationRetrievalState(
  props: ConversationRetrievalStateProps & { business?: boolean },
) {
  const { t, i18n } = useTranslation();
  const spanishBusiness = props.business && (i18n.resolvedLanguage ?? i18n.language).startsWith("es");

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
      <p className="text-[13px] text-black/60 dark:text-white/65">
        {spanishBusiness ? "Cuadrando…" : t("chat.opening_conversation", "Opening conversation…")}
      </p>
    </div>
  );
}
