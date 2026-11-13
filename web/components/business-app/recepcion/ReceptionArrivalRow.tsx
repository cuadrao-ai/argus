"use client";

import { Trash2 } from "lucide-react";
import { ChatCircle } from "@phosphor-icons/react";
import { Tooltip } from "@/components/ui/Tooltip";
import ReceptionCutText, { useCutOff } from "./ReceptionCutText";
import ReceptionStatus from "./ReceptionStatus";
import { CHANNEL_ICON } from "../foundation/channel-icons";
import { useTranslation } from "react-i18next";
import { currencySymbol } from "@/lib/money-entry";
import { Unknown } from "../transacciones/transacciones-parts";
import { resolveLanguage } from "@/lib/language-features";
import type { BusinessPanelState } from "../BusinessWorkspace";
import { formatAmount, formatMoney, formatRelativeTime, UNKNOWN_VALUE } from "../business-format";
import { isOpenRecord } from "../record-tray";
import { receptionSender, receptionDocumentTitle, receptionTarget, type ReceptionRow, type ReceptionView } from "./reception-model";
import type { ReceptionPreferences } from "./ReceptionControls";
import ReceptionOriginal from "./ReceptionOriginal";
import styles from "./reception.module.css";

export default function ReceptionArrivalRow({ row, view, panel, openPanel, preferences, selectable, checkable, checked, unseen, onCheck, onDelete }: { onDelete?: () => void; row: ReceptionRow; view: ReceptionView; selectable: boolean; checkable: boolean; checked: boolean; unseen: boolean; onCheck: () => void; panel: BusinessPanelState; openPanel: (panel: BusinessPanelState) => void; preferences: ReceptionPreferences }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const word = (key: string) => t(`business.reception_preview.${key}`);
  const receipt = row.kind === "receipt" ? row.receipt : null;
  const target = receptionTarget(row);
  const open = () => openPanel(target);
  const title = receptionDocumentTitle(row, { untitled: t("business.receipt.untitled"), pending: word("intake_pending"), exception: word("intake_exception"), text: word("text_intake") });
  const money = receipt && preferences.amount ? formatMoney(receipt.amount, receipt.currency, locale) : null;
  const sender = receptionSender(row);
  const SourceIcon = CHANNEL_ICON[row.source];
  const selected = isOpenRecord(panel, target);
  const [titleRef, titleCut] = useCutOff<HTMLSpanElement>(title);
  const arrival = preferences.arrival ? <time dateTime={row.receivedAt} title={new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(row.receivedAt))}>{formatRelativeTime(row.receivedAt, locale)}</time> : null;
  const identity = <button type="button" onClick={open} className={styles.identity}>
    <span className={styles.documentText}>{unseen ? <span className={styles.unseenDot} aria-hidden="true" /> : null}<span ref={titleRef} className={styles.title}>{unseen ? <span className="sr-only">{word("unseen")}: </span> : null}{row.kind === "note" ? <ChatCircle className={styles.noteIcon} size={15} aria-hidden="true" /> : null}{title}</span>{money ? <span className={`${styles.mobileMoney} cuadrao-amount`}>{money}</span> : null}</span>
  </button>;
  return <li className={styles.row} data-selected={selected} data-checked={checkable && checked} data-unseen={unseen} aria-current={selected ? "true" : undefined} data-testid="reception-row" data-kind={row.kind} onClick={event => { if (!(event.target as HTMLElement).closest("button,input,label,a")) open(); }}>
    {!selectable ? null : checkable ? <label className={styles.checkbox}><input type="checkbox" checked={checked} onChange={onCheck} aria-label={t("business.reception_preview.select_document", { name: title })} /></label> : <span className={styles.checkbox} />}
    {titleCut ? <Tooltip content={title} side="top">{identity}</Tooltip> : identity}
    <span className={styles.fileCell} data-file={!!receipt || row.kind === "note"}>{receipt ? <ReceptionOriginal receipt={receipt} /> : row.kind === "note" ? <Unknown meaning={word("without_file")} /> : <Unknown meaning={word("no_file")} />}</span>
    {preferences.source || preferences.sender || preferences.arrival ? <span className={styles.source} data-info={preferences.source || preferences.sender} data-testid="reception-source">
      {preferences.source ? <span className={styles.channel} data-testid="reception-channel"><SourceIcon size={15} aria-hidden="true" />{word(`source_${row.source}`)}</span> : null}
      {!preferences.sender ? null : sender ? <ReceptionCutText text={sender} className={styles.sender} data-known="true" data-testid="reception-sender" /> : <span className={styles.sender} data-known="false" data-testid="reception-sender" title={t("business.email.no_sender")} aria-label={t("business.email.no_sender")}>{UNKNOWN_VALUE}</span>}
      {arrival ? <span className={styles.mobileArrival}>{arrival}</span> : null}
    </span> : null}
    {preferences.amount ? <span data-testid="reception-amount" className={`${styles.amountCell} cuadrao-amount`}>{receipt?.amount != null && receipt.currency ? formatAmount(receipt.amount, receipt.currency, locale) : <Unknown />}</span> : null}
    {preferences.currency ? <span data-testid="reception-currency" className={styles.currencyCell}>{receipt?.currency ? currencySymbol(receipt.currency) : <Unknown />}</span> : null}
    {view === "listos" ? null : <ReceptionStatus row={row} reasonOnly={view === "attention"} />}
    {arrival ? <span className={styles.arrival}>{arrival}</span> : null}
    <div className={styles.rowActions}>{onDelete ? <Tooltip content={t("business.document_delete.delete")} side="top"><button type="button" className={`${styles.trashAction} rounded-full`} onClick={onDelete} aria-label={t("business.document_delete.label", { name: title })}><Trash2 size={17} aria-hidden="true" /></button></Tooltip> : null}<button type="button" className={`${styles.rowAction} rounded-full`} onClick={open}><span>{word("placeholder.open")}</span></button></div>
  </li>;
}
