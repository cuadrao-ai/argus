"use client";

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessSourceEvidence } from "@/lib/business-dossier";
import { formatTimestamp } from "./business-format";
import { SURFACE_CARD } from "./foundation/surfaces";
import { resolveLanguage } from "@/lib/language-features";

/** The text with each exact occurrence of a value marked; no value is guessed at or reformatted. */
export function markValues(text: string, values: readonly string[]): ReactNode {
  const needles = values.filter((value) => value.length > 1);
  if (!needles.length) return text;
  const parts: ReactNode[] = [];
  let at = 0;
  while (at < text.length) {
    let found = -1;
    let needle = "";
    for (const value of needles) {
      const index = text.indexOf(value, at);
      if (index >= 0 && (found < 0 || index < found || (index === found && value.length > needle.length))) { found = index; needle = value; }
    }
    if (found < 0) break;
    if (found > at) parts.push(text.slice(at, found));
    parts.push(<mark key={found} className="rounded-mark bg-[#f2e1b8] px-0.5 text-inherit dark:bg-[#5a4a26]">{needle}</mark>);
    at = found + needle.length;
  }
  if (!parts.length) return text;
  if (at < text.length) parts.push(text.slice(at));
  return parts;
}

export default function ReceiptMessages({ sources, highlight = [] }: { sources: BusinessSourceEvidence[]; /** Values from the form row in focus, marked where they appear verbatim. */ highlight?: readonly string[] }) {
  const { t, i18n } = useTranslation();
  const messages = sources.filter((source): source is Extract<BusinessSourceEvidence, { text: string }> => source.kind === "message");
  const proposals = sources.filter((source): source is Extract<BusinessSourceEvidence, { text: string }> => source.kind === "agent_proposal");
  const actions = sources.filter((source): source is Extract<BusinessSourceEvidence, { text: string }> => source.kind === "web_action");
  if (!messages.length && !proposals.length && !actions.length) return null;
  return (
    <div className="space-y-4">
    {messages.length ? <section className={SURFACE_CARD} aria-label={t("business.dossier.messages_title", { count: messages.length, defaultValue: "Original message" })} data-testid="receipt-messages">
      <h3 className="text-[14px] font-medium text-black dark:text-white">{t("business.dossier.messages_title", { count: messages.length, defaultValue: "Original message" })}</h3>
      <ol className="mt-4 space-y-4">
        {messages.map((source) => (
          <li key={source.id}>
            <p className="text-[12px] text-black/55 dark:text-white/55">{source.channel === "whatsapp" ? "WhatsApp" : t("business.dossier.web_message", "Web message")} · {formatTimestamp(source.received_at, i18n.resolvedLanguage ?? resolveLanguage({}))}</p>
            <blockquote className="mt-2 whitespace-pre-wrap break-words border-l-2 border-black/10 pl-3 text-[15px] leading-relaxed text-black/80 dark:border-white/15 dark:text-white/80">{source.text ? markValues(source.text, highlight) : t("business.dossier.message_unavailable", "The original message isn't available.")}</blockquote>
          </li>
        ))}
      </ol>
    </section> : null}
    {proposals.length ? <section className={SURFACE_CARD} aria-label={t("business.dossier.proposals", "Agent proposals")}>
      <h3 className="text-[14px] font-medium text-black dark:text-white">{t("business.dossier.proposals", "Agent proposals")}</h3>
      <ol className="mt-4 space-y-4">{proposals.map((source) => <li key={source.id}>
        <p className="text-[12px] text-black/55 dark:text-white/55">{source.channel === "whatsapp" ? "WhatsApp" : t("business.dossier.web_message", "Web message")} · {formatTimestamp(source.received_at, i18n.resolvedLanguage ?? resolveLanguage({}))}</p>
        <blockquote className="mt-2 whitespace-pre-wrap break-words border-l-2 border-black/10 pl-3 text-[15px] leading-relaxed text-black/80 dark:border-white/15 dark:text-white/80">{source.text}</blockquote>
      </li>)}</ol>
    </section> : null}
    {actions.length ? <section className={SURFACE_CARD} aria-label={t("business.dossier.web_actions", "Web review actions")}>
      <h3 className="text-[14px] font-medium text-black dark:text-white">{t("business.dossier.web_actions", "Web review actions")}</h3>
      <ol className="mt-4 space-y-4">
        {actions.map((source) => <li key={source.id}>
          <p className="text-[12px] text-black/55 dark:text-white/55">{formatTimestamp(source.received_at, i18n.resolvedLanguage ?? resolveLanguage({}))}</p>
          <details className="mt-2">
            <summary className="min-h-11 cursor-pointer rounded-item text-[13px] text-black/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/20 dark:text-white/70">{t("business.dossier.submitted_action", "Original submitted action")}</summary>
            <pre className="mt-2 whitespace-pre-wrap break-words text-[12px] leading-relaxed text-black/65 dark:text-white/65">{source.text}</pre>
          </details>
        </li>)}
      </ol>
    </section> : null}
    </div>
  );
}
