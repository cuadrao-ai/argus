"use client";

import { useTranslation } from "react-i18next";
import type { BusinessSourceEvidence } from "@/lib/business-dossier";
import { formatTimestamp } from "./business-format";
import { cardClass } from "./business-ui";

export default function ReceiptMessages({ sources }: { sources: BusinessSourceEvidence[] }) {
  const { t, i18n } = useTranslation();
  const messages = sources.filter((source): source is Extract<BusinessSourceEvidence, { text: string }> => source.kind === "message");
  const actions = sources.filter((source): source is Extract<BusinessSourceEvidence, { text: string }> => source.kind === "web_action");
  if (!messages.length && !actions.length) return null;
  return (
    <div className="space-y-4">
    {messages.length ? <section className={cardClass} aria-label={t("business.dossier.messages", "Original messages")}>
      <h3 className="text-[14px] font-medium text-black dark:text-white">{t("business.dossier.messages", "Original messages")}</h3>
      <ol className="mt-4 space-y-4">
        {messages.map((source) => (
          <li key={source.id}>
            <p className="text-[12px] text-black/55 dark:text-white/55">{source.channel === "whatsapp" ? "WhatsApp" : t("business.dossier.web_message", "Web message")} · {formatTimestamp(source.received_at, i18n.resolvedLanguage ?? "en")}</p>
            <blockquote className="mt-2 whitespace-pre-wrap break-words border-l-2 border-black/10 pl-3 text-[15px] leading-relaxed text-black/80 dark:border-white/15 dark:text-white/80">{source.text ?? t("business.dossier.message_unavailable", "The original message isn't available.")}</blockquote>
          </li>
        ))}
      </ol>
    </section> : null}
    {actions.length ? <section className={cardClass} aria-label={t("business.dossier.web_actions", "Web review actions")}>
      <h3 className="text-[14px] font-medium text-black dark:text-white">{t("business.dossier.web_actions", "Web review actions")}</h3>
      <ol className="mt-4 space-y-4">
        {actions.map((source) => <li key={source.id}>
          <p className="text-[12px] text-black/55 dark:text-white/55">{formatTimestamp(source.received_at, i18n.resolvedLanguage ?? "en")}</p>
          <details className="mt-2">
            <summary className="min-h-11 cursor-pointer text-[13px] text-black/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/20 dark:text-white/70">{t("business.dossier.submitted_action", "Original submitted action")}</summary>
            <pre className="mt-2 whitespace-pre-wrap break-words text-[12px] leading-relaxed text-black/65 dark:text-white/65">{source.text}</pre>
          </details>
        </li>)}
      </ol>
    </section> : null}
    </div>
  );
}
