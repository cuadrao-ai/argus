"use client";

import { ArrowRight, Eye, EnvelopeSimple, ChatCircle, UploadSimple, NotePencil, WhatsappLogo } from "@phosphor-icons/react";
import ReceptionStatus from "./ReceptionStatus";
import { useTranslation } from "react-i18next";
import { currencySymbol } from "@/lib/money-entry";
import { Unknown } from "../transacciones/transacciones-parts";
import { resolveLanguage } from "@/lib/language-features";
import { useBusiness, type BusinessPanelState } from "../BusinessWorkspace";
import { formatAmount, formatMoney, formatRelativeTime } from "../business-format";
import { isOpenRecord } from "../record-tray";
import { receptionAction, receptionSender, receptionDocumentTitle, type ReceptionRow } from "./reception-model";
import type { ReceptionPreferences } from "./ReceptionControls";
import ReceptionOriginal from "./ReceptionOriginal";
import styles from "./reception.module.css";

export const SOURCE_ICONS = { web: UploadSimple, email: EnvelopeSimple, whatsapp: WhatsappLogo, note: NotePencil };
export default function ReceptionArrivalRow({ row, panel, openPanel, preferences, selectable, checked, unseen, onCheck, onSeen, onInspect, inspecting }: { onInspect: () => void; inspecting: boolean; selectable: boolean; checked: boolean; unseen: boolean; onCheck: () => void; onSeen: () => void; row: ReceptionRow; panel: BusinessPanelState; openPanel: (panel: BusinessPanelState) => void; preferences: ReceptionPreferences }) {
  const { t, i18n } = useTranslation();
  const { chosen } = useBusiness();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const word = (key: string) => t(`business.reception_preview.${key}`);
  const receipt = row.kind === "receipt" ? row.receipt : null;
  const target: BusinessPanelState = row.kind === "receipt" ? { kind: "receipt", receiptId: row.id, list: "inbox" } : row.kind === "note" ? { kind: "draft", draftId: row.id, list: "inbox" } : row.kind === "email" ? { kind: "email", emailId: row.id } : { kind: "inbox" };
  const title = receptionDocumentTitle(row, { untitled: t("business.receipt.untitled"), pending: word("intake_pending"), exception: word("intake_exception"), text: word("text_intake") });
  const money = receipt && preferences.amount ? formatMoney(receipt.amount, receipt.currency, locale) : null;
  const sender = receptionSender(row);
  const action = receipt?.expense_id ? "action_record" : receptionAction(row, chosen?.capabilities.includes("prepare") === true);
  const SourceIcon = SOURCE_ICONS[row.source];
  const open = (target: BusinessPanelState) => { onSeen(); openPanel(target); };
  const selected = inspecting || (row.kind !== "message" && isOpenRecord(panel, target));
  const arrival = preferences.arrival ? <time dateTime={row.receivedAt} title={new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(row.receivedAt))}>{formatRelativeTime(row.receivedAt, locale)}</time> : null;
  return <li className={styles.row} data-selected={selected} data-checked={checked} data-unseen={unseen} aria-current={selected ? "true" : undefined} data-testid="reception-row" data-kind={row.kind} onClick={event => { if (!(event.target as HTMLElement).closest("button,input,label,a")) onInspect(); }}>
    {selectable ? <label className={styles.checkbox}><input type="checkbox" checked={checked} onChange={onCheck} aria-label={t("business.reception_preview.select_document", { name: title })} /></label> : null}
    <button type="button" onClick={onInspect} className={styles.identity}>
      <span className={styles.documentText}>{unseen ? <span className={styles.unseenDot} aria-hidden="true" /> : null}<span className={styles.title}>{unseen ? <span className="sr-only">{word("unseen")}: </span> : null}{row.kind === "note" || row.kind === "message" ? <ChatCircle className={styles.noteIcon} size={15} aria-hidden="true" /> : null}{title}</span>{money ? <span className={`${styles.mobileMoney} cuadrao-amount`}>{money}</span> : null}</span>
    </button>
    <span className={styles.fileCell} data-file={!!receipt || row.kind === "note" || row.kind === "message"}>{receipt ? <ReceptionOriginal receipt={receipt} onOpen={onSeen} /> : row.kind === "note" || row.kind === "message" ? <Unknown meaning={word("without_file")} /> : <Unknown meaning={word("no_file")} />}</span>
    {preferences.source || preferences.sender || preferences.arrival ? <span className={styles.source} data-info={preferences.source || preferences.sender} data-testid="reception-source">
      {preferences.source ? <span className={styles.channel} data-testid="reception-channel"><SourceIcon size={15} aria-hidden="true" />{word(`source_${row.source}`)}</span> : null}
      {preferences.sender ? <span className={styles.sender} data-known={!!sender} data-testid="reception-sender" title={sender || t("business.email.no_sender")} aria-label={sender ? undefined : t("business.email.no_sender")}>{sender || "–"}</span> : null}
      {arrival ? <span className={styles.mobileArrival}>{arrival}</span> : null}
    </span> : null}
    {preferences.amount ? <span data-testid="reception-amount" className={`${styles.amountCell} cuadrao-amount`}>{receipt?.amount != null && receipt.currency ? formatAmount(receipt.amount, receipt.currency, locale) : <Unknown />}</span> : null}
    {preferences.currency ? <span data-testid="reception-currency" className={styles.currencyCell}>{receipt?.currency ? currencySymbol(receipt.currency) : <Unknown />}</span> : null}
    <ReceptionStatus row={row} />
    {arrival ? <span className={styles.arrival}>{arrival}</span> : null}
    <button type="button" className={styles.rowAction} onClick={() => action === "action_detail" || action === "action_note" ? onInspect() : receipt?.expense_id ? open({ kind: "expense", expenseId: receipt.expense_id }) : open(target)}><span>{(action === "action_detail" || action === "action_note") ? <Eye size={15} aria-hidden="true" /> : <ArrowRight size={15} aria-hidden="true" />}{word(action)}</span></button>
  </li>;
}
