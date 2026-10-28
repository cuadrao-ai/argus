"use client";

import { useEffect, useRef, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { resolveLanguage } from "@/lib/language-features";
import { BusinessContext, useBusiness, type BusinessPanelState } from "../BusinessWorkspace";
import { EmailDeliveryDetail } from "../BusinessEmailDeliveries";
import ReceiptSourcePreview from "../ReceiptSourcePreview";
import { formatTimestamp, formatMoney } from "../business-format";
import { primaryButtonClass } from "../business-ui";
import { CHANNEL_ICON } from "../foundation/channel-icons";
import { receptionAction, receptionDocumentTitle, receptionSender, type ReceptionRow } from "./reception-model";
import ReceptionStatus from "./ReceptionStatus";
import styles from "./reception.module.css";

export type ReceptionDossierProps = { live: boolean; row: ReceptionRow; onClose: () => void; onNavigate: (next: BusinessPanelState) => void; returnFocusRef: RefObject<HTMLElement | null> };
export function receptionReviewTarget(row: ReceptionRow): BusinessPanelState | null {
  if (row.kind === "receipt") return row.receipt.expense_id ? { kind: "expense", expenseId: row.receipt.expense_id } : { kind: "receipt", receiptId: row.id, list: "inbox" };
  if (row.kind === "note") return { kind: "draft", draftId: row.id, list: "inbox" };
  if (row.kind === "email") return { kind: "email", emailId: row.id };
  return null;
}
/** Opening a ready receipt acknowledges it for this person through the same server route as the record panel. Nothing is marked seen locally. */
function useAcknowledgeOnOpen(row: ReceptionRow, live: boolean) {
  const { source, reload } = useBusiness();
  const sent = useRef<string | null>(null);
  const activity = row.kind === "receipt" ? row.receipt.activity : null;
  const id = row.kind === "receipt" ? row.id : null;
  const cursor = activity?.state === "ready" && activity.unread ? activity.completion_cursor : null;
  useEffect(() => {
    if (!live || !id || !cursor || !source.markReceiptRead || sent.current === cursor) return;
    sent.current = cursor;
    const request = source.markReceiptRead(id, cursor);
    request.then(result => { if (result.completion_cursor === cursor && !result.unread) reload(); }, () => { sent.current = null; });
  }, [live, id, cursor, source, reload]);
}

export default function ReceptionDossier({ live, row, onClose, onNavigate, returnFocusRef }: ReceptionDossierProps) {
  const { t, i18n } = useTranslation();
  const business = useBusiness();
  const { chosen, source, records, emailRefresh } = business;
  const word = (key: string) => t(`business.reception_preview.${key}`);
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  useAcknowledgeOnOpen(row, live);
  const heading = useRef<HTMLHeadingElement>(null);
  const section = useRef<HTMLElement>(null);
  const focused = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const host = section.current;
    if (!host) return;
    // A successful retry removes its button. Keep keyboard focus in this dossier.
    const observer = new MutationObserver(() => {
      if (host.isConnected && focused.current && !focused.current.isConnected && document.activeElement === document.body) {
        heading.current?.focus({ preventScroll: true });
      }
    });
    observer.observe(host, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);
  const title = receptionDocumentTitle(row, { untitled: t("business.receipt.untitled"), pending: word("intake_pending"), exception: word("intake_exception"), text: word("text_intake") });
  const sender = receptionSender(row);
  const text = row.kind === "message" ? row.text : row.kind === "note" ? row.note.text : row.kind === "receipt" ? row.receipt.source_text : null;
  const target = receptionReviewTarget(row);
  const action = row.kind === "receipt" && row.receipt.expense_id ? "action_record" : row.kind === "note" ? "action_review" : receptionAction(row, chosen?.capabilities.includes("prepare") === true);
  const showAction = target && row.kind !== "email" && (action === "action_review" || action === "action_resolve" || action === "action_record");
  const amount = row.kind === "receipt" ? formatMoney(row.receipt.amount, row.receipt.currency, locale) : null;
  return <AdaptivePanel modal={false} width="dossier" title={t("business.tray.title", "Details")} closeLabel={t("common.close")} onClose={onClose} returnFocusRef={returnFocusRef} initialFocusRef={heading} snaps={["full"]} initialSnap="full" footer={showAction ? <div className={styles.detailFooter}><button type="button" className={primaryButtonClass} onClick={() => onNavigate(target)}>{word(action)}</button></div> : undefined}>
    <BusinessContext.Provider value={{ ...business, openPanel: onNavigate }}>
      <section ref={section} onFocusCapture={event => { focused.current = event.target as HTMLElement; }} className={styles.detail} data-testid="reception-dossier" data-kind={row.kind}>
        {/* The dossier's two columns: what arrived and from where on the left, the original itself on the right. */}
        <div className={styles.detailColumns}>
        <div className={styles.detailMain}>
        <header className={styles.detailHeader}><h2 ref={heading} tabIndex={-1}>{title}</h2>{row.kind !== "email" ? <ReceptionStatus row={row} full /> : null}</header>
        <section aria-label={word("arrival_context")} className={styles.detailContext}>
          <h3>{word("arrival_context")}</h3>
          <dl>
            <dt>{word("source")}</dt><dd>{(() => { const Icon = CHANNEL_ICON[row.source as keyof typeof CHANNEL_ICON]; return <span className={styles.channelValue}>{Icon ? <Icon size={16} aria-hidden="true" /> : null}{word(`source_${row.source}`)}</span>; })()}</dd>
            <dt>{word("sender")}</dt><dd data-testid="reception-detail-sender">{sender || t("business.email.no_sender")}</dd>
            <dt>{word("arrival")}</dt><dd><time dateTime={row.receivedAt}>{formatTimestamp(row.receivedAt, locale)}</time></dd>
            {row.kind === "message" || row.kind === "note" ? <><dt>{word("file")}</dt><dd>{word("without_file")}</dd></> : null}
          </dl>
        </section>
        {row.kind === "message" ? <p className={styles.detailPreview}>{word("note_preview_help")}</p> : null}
        </div>
        <div className={styles.detailSide}>
        {row.kind === "receipt" ? <section className={styles.detailOriginal} aria-label={word("original_content")}><h3>{word("original_content")}</h3><ReceiptSourcePreview detail={row.receipt} initialExpanded showArrivalContext={false} />{amount ? <dl className={styles.detailAmount}><dt>{word("extracted_amount")}</dt><dd className="cuadrao-amount">{amount}</dd></dl> : null}</section> : null}
        {text ? <section className={styles.detailText} aria-label={word(row.kind === "receipt" ? "original_caption" : "original_message")}><h3>{word(row.kind === "receipt" ? "original_caption" : "original_message")}</h3><blockquote data-testid="reception-original-text">{text}</blockquote></section> : null}
        {row.kind === "email" ? <section className={styles.detailEmail} aria-label={word("original_email")}><h3>{word("original_email")}</h3><EmailDeliveryDetail delivery={row.email.delivery} inbox={records.inbox} loadDetail={source.emailDelivery} retryDelivery={async id => { await source.retryEmailDelivery(id); emailRefresh.refresh(); }} openReceipt={id => onNavigate({ kind: "receipt", receiptId: id, list: "inbox" })} /></section> : null}
        </div>
        </div>
      </section>
    </BusinessContext.Provider>
  </AdaptivePanel>;
}
