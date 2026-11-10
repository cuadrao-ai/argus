"use client";

// Inicio's left card, Necesita atención: what waits in the Bandeja, problems first, as the Bandeja itself words it.
// The count is the server's one Bandeja number, the one the sidebar shows; a row never shows an amount.

import { CircleCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { resolveLanguage } from "@/lib/language-features";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { useBusiness } from "../BusinessWorkspace";
import { formatRelativeTime } from "../business-format";
import { canAddRecords, quietButtonClass, secondaryButtonClass } from "../business-ui";
import { useEmailWords } from "../BusinessEmailDeliveries";
import { inboxCount } from "../inbox-count";
import { CHANNEL_ICON } from "../foundation/channel-icons";
import { FOCUS_RING } from "../foundation/presentation";
import { receptionDocumentTitle, receptionRows, receptionTarget, type ReceptionRow } from "../recepcion/reception-model";
import { BANDEJA_REASON_KEY, receptionTag } from "../recepcion/reception-status";
import { HomeCard, HOME_MUTED, HOME_SKELETON, HOME_TYPE } from "./HomeCard";

/** Rows the card shows; "Ver todo" opens the rest in the Bandeja. */
export const ATTENTION_ROWS = 6;

/** A row that needs a fix: the Bandeja's attention tag, except a written note, which only waits to be reviewed. */
export const attentionProblem = (row: ReceptionRow) => row.kind !== "note" && receptionTag(row).tag === "attention";

/** Problems first, then the rest, each keeping the Bandeja's own order. */
export function attentionRows(rows: readonly ReceptionRow[]): ReceptionRow[] {
  return [...rows.filter(attentionProblem), ...rows.filter((row) => !attentionProblem(row))].slice(0, ATTENTION_ROWS);
}

const TAG = `inline-flex items-center gap-1 rounded-mark px-1.5 py-0.5 ${HOME_TYPE.tag} font-medium`;
const NEUTRAL = `${TAG} bg-black/5 text-[#56635e] dark:bg-white/10 dark:text-white/70`;
const ALERT = `${TAG} bg-[#f6dfe0] text-[#9e2f39] dark:bg-[#4a2a2f] dark:text-[#ec9aa0]`;

function SkeletonRows() {
  const { t } = useTranslation();
  return (
    <ul role="status" aria-busy="true" data-testid="home-attention-loading">
      <li className="sr-only">{t("business.inicio.attention.loading")}</li>
      {Array.from({ length: ATTENTION_ROWS }, (_, index) => (
        <li key={index} aria-hidden="true" className="flex h-[62px] items-center gap-3 border-b border-[color:var(--surface-divider)] px-5 last:border-b-0">
          <span className={`h-8 w-8 shrink-0 rounded-full ${HOME_SKELETON}`} />
          <span className="min-w-0 flex-1 space-y-2"><span className={`block h-4 w-2/5 rounded-mark ${HOME_SKELETON}`} /><span className={`block h-3.5 w-1/3 rounded-mark ${HOME_SKELETON}`} /></span>
          <span className={`h-4 w-16 shrink-0 rounded-mark ${HOME_SKELETON}`} />
        </li>
      ))}
    </ul>
  );
}

/**
 * The five states: rows; the first day (no document ever: what this card is for and the one way to add); all caught
 * up (documents exist, none waiting); loading (row shapes, no count, never "Todo al día" before the server counted);
 * and a failed read (its reference and Reintentar, never a zero). Someone who may not prepare sees the rows without
 * a verb. `firstDay` is the server's "no document ever" (no approved month yet), null while unknown.
 */
export function HomeAttention({ firstDay }: { firstDay: boolean | null }) {
  const { records, openPanel, reload, chosen, actions } = useBusiness();
  const emailWords = useEmailWords();
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const prepares = canAddRecords(chosen);
  const total = inboxCount(records);
  const waiting = receptionRows(records.inbox ?? [], records.notes ?? [], records.emails ?? []);
  const listsIn = records.inbox !== null && (records.notes !== null || Boolean(records.notesFailure)) && (records.emails !== null || Boolean(records.emailsFailure));
  const failed = records.error || (total === null && Boolean(records.serverReference));
  const seeAll = (
    <button type="button" data-testid="home-attention-see-all" className={`${quietButtonClass} ${HOME_TYPE.action}`} onClick={() => openPanel({ kind: "inbox" })}>
      {t("business.inicio.attention.see_all")}
    </button>
  );
  const card = (body: React.ReactNode, count: number | null = null) => (
    <HomeCard testId="home-attention" title={t("business.inicio.attention.title")} count={count} action={seeAll}>{body}</HomeCard>
  );

  if (failed) {
    const reference = records.failureReference ?? records.serverReference;
    return card(
      <div role="alert" data-testid="home-attention-error" className="flex flex-col items-center gap-3 px-5 py-6 text-center">
        <p className="text-[16px] text-[#172b26] dark:text-white">{t("business.inicio.attention.error")}</p>
        {/* A refusal for good offers no Reintentar, which cannot help, and says whom to write instead. */}
        {records.refused ? <p className={`${HOME_TYPE.secondary} ${HOME_MUTED}`}>{t("auth.business_unavailable.body")}</p> : null}
        {reference ? <ReferenceCode reference={reference} /> : null}
        {records.refused ? null : <button type="button" className={secondaryButtonClass} onClick={reload}>{t("common.retry")}</button>}
      </div>,
    );
  }
  // Rows show once their lists are in, with a count only once the server has counted; an empty card waits for that
  // count and for whether any document ever arrived.
  // The server's count decides an empty card: zero is empty whatever rows another list still holds.
  const empty = total === 0 || (total === null && waiting.length === 0);
  if (!listsIn || (empty && (total === null || firstDay === null))) return card(<SkeletonRows />);

  if (empty) {
    if (firstDay) {
      const add = prepares ? actions.create.find((action) => action.id === "upload_receipt") : undefined;
      return card(
        <div data-testid="home-attention-first-day" className="flex flex-col items-center gap-2 px-5 py-6 text-center">
          <p className="text-[16px] font-medium text-[#172b26] dark:text-white">{t("business.inicio.attention.first_day_title")}</p>
          <p className={`max-w-sm ${HOME_TYPE.secondary} ${HOME_MUTED}`}>{t("business.inicio.attention.first_day_body")}</p>
          {add ? <button type="button" data-testid="home-attention-add" className={`mt-2 ${secondaryButtonClass}`} onClick={add.run}>{t("business.inicio.attention.first_day_add")}</button> : null}
        </div>,
      );
    }
    return card(
      <div data-testid="home-attention-clear" className="flex flex-col items-center gap-1 px-5 py-5 text-center">
        <p className="flex items-center gap-2 text-[16px] font-medium text-[#172b26] dark:text-white"><CircleCheck className="h-5 w-5 shrink-0 text-[var(--cuadrao-green)]" aria-hidden="true" />{t("business.inicio.attention.clear_title")}</p>
        <p className={`${HOME_TYPE.secondary} ${HOME_MUTED}`}>{t("business.inicio.attention.clear_body")}</p>
      </div>,
    );
  }

  const title = (row: ReceptionRow) => {
    // The supplier once read; before that, the source: a WhatsApp photo has no file name of its own.
    if (row.kind === "receipt" && row.source === "whatsapp" && !row.receipt.filename?.trim() && !(row.receipt.merchant?.trim() && row.receipt.attention !== "unreadable")) return t("business.inicio.attention.whatsapp_photo");
    return receptionDocumentTitle(row, { untitled: t("business.inicio.attention.untitled"), pending: t("business.reception_preview.intake_pending"), exception: t("business.reception_preview.intake_exception"), text: t("business.reception_preview.text_intake") });
  };
  // The Bandeja's own words for each row: its reason for a problem, its state otherwise.
  const tag = (row: ReceptionRow) => {
    const state = receptionTag(row);
    if (row.kind === "note") return <span className={NEUTRAL}>{t("business.inbox.row_note")}</span>;
    if (attentionProblem(row)) {
      const reason = row.kind === "email" ? emailWords.noReceipt(row.email.delivery) : state.tag === "attention" && state.reason && BANDEJA_REASON_KEY[state.reason] ? t(BANDEJA_REASON_KEY[state.reason]) : t("business.attention_short.other");
      return <span data-tone="attention" className={ALERT}><span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />{reason}</span>;
    }
    const word = state.tag === "reading" ? t(row.kind === "email" && row.email.delivery.waiting ? "business.email.waiting_label" : "business.inbox.row_reading") : t("business.inbox.row_ready");
    return <span className={NEUTRAL}>{word}</span>;
  };
  return card(
    <ul data-testid="home-attention-rows">
      {attentionRows(waiting).map((row) => {
        const Icon = CHANNEL_ICON[row.source];
        const verb = prepares ? t(attentionProblem(row) ? "business.inicio.attention.resolve" : "business.inicio.attention.review") : null;
        return (
          <li key={`${row.kind}:${row.id}`} data-kind={row.kind} data-problem={attentionProblem(row) ? "true" : undefined} className="border-b border-[color:var(--surface-divider)] last:border-b-0">
            <button type="button" onClick={() => openPanel(receptionTarget(row))} className={`flex min-h-[62px] w-full items-center gap-3 px-5 py-1.5 text-left transition-colors duration-[80ms] hover:bg-black/[0.03] dark:hover:bg-white/[0.04] ${FOCUS_RING}`}>
              <span aria-hidden="true" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[color:var(--surface-divider)] bg-[var(--cuadrao-cream)] text-[#56635e] dark:bg-white/[0.06] dark:text-white/70"><Icon size={16} /></span>
              <span className="min-w-0 flex-1">
                <span data-testid="home-attention-title" className={`block truncate ${HOME_TYPE.rowTitle} font-medium text-[#172b26] dark:text-white`}>{title(row)}</span>
                <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  {tag(row)}
                  <span data-testid="home-attention-time" className={`${HOME_TYPE.secondary} ${HOME_MUTED}`}>{formatRelativeTime(row.receivedAt, locale)}</span>
                </span>
              </span>
              {verb ? <span data-testid="home-attention-verb" className={`shrink-0 ${HOME_TYPE.action} font-medium text-[var(--cuadrao-green)]`}>{verb}</span> : null}
            </button>
          </li>
        );
      })}
    </ul>,
    total,
  );
}
