"use client";

import { Fragment, type CSSProperties, type ReactNode } from "react";
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
import { sentByName } from "@/lib/sent-by";
import type { BusinessPanelState } from "../BusinessWorkspace";
import { formatAmount, formatDate, formatMoney, formatRelativeTime } from "../business-format";
import { isOpenRecord } from "../record-tray";
import { receptionChannelKey, receptionSentBy, receptionDocumentTitle, receptionTarget, type ReceptionRow } from "./reception-model";
import type { ReceptionColumnKey, ReceptionPreferences } from "./reception-columns";
import { originPlace, receptionPlaces } from "./reception-grid";
import ReceptionOriginal from "./ReceptionOriginal";
import motion from "../business-skeletons.module.css";
import styles from "./reception.module.css";

type CellProps = { style: CSSProperties; "data-testid": string };
type Places = ReturnType<typeof receptionPlaces>;

/**
 * A row's places: the box, Contenido, the person's columns in their order with Canal, Enviado por and the phone's
 * arrival in one shared cell, then the actions. A loaded row and a pending row both draw through it.
 */
function RowPlaces({ places, box, identity, origin, cells, actions }: { places: Places; box: ReactNode; identity: ReactNode; origin: ReactNode; cells: Record<ReceptionColumnKey, ReactNode>; actions: ReactNode }) {
  const together = originPlace(places.shown);
  return <>{box}{identity}{places.shown.map(key => <Fragment key={key}>{key === together ? origin : null}{cells[key]}</Fragment>)}<div className={styles.rowActions} style={places.last}>{actions}</div></>;
}

function Bar({ width, height = 12, pill = false }: { width: number | string; height?: number; pill?: boolean }) {
  return <span className={`${motion.block} ${motion.shimmer} ${styles.skeletonBar} ${pill ? "rounded-full" : "rounded-mark"}`} style={{ width, height }} />;
}

/** A row while the list's first page loads: the same places and cell boxes as a loaded row, each value a placeholder bar. */
export function ReceptionPendingRow({ index, preferences, selectable }: { index: number; preferences: ReceptionPreferences; selectable: boolean }) {
  const places = receptionPlaces(preferences);
  const has = places.has;
  const channel = (style?: CSSProperties) => has("source") ? <span className={styles.channel} style={style}><Bar width={76} /></span> : null;
  const sender = (style?: CSSProperties) => has("sender") ? <span className={styles.sender} style={style} data-known="true"><Bar width={index % 2 ? 110 : 150} /></span> : null;
  return <li className={`${styles.row} ${styles.skeletonRow}`} aria-hidden="true">
    <RowPlaces places={places}
      box={selectable ? <span className={styles.checkbox}><Bar width={16} height={16} /></span> : null}
      identity={<span className={styles.identity}><Bar width={index % 2 ? 170 : 220} height={15} /></span>}
      origin={<span className={styles.source} style={places.shared} data-info={has("source") || has("sender")}>{sender()}{channel()}{has("arrival") ? <span className={styles.mobileArrival}><Bar width={65} /></span> : null}</span>}
      cells={{
        file: <span className={styles.fileCell} style={places.at("file")} data-file="true"><Bar width={18} height={20} /></span>,
        source: channel(places.at("source")),
        sender: sender(places.at("sender")),
        amount: <span className={styles.amountCell} style={places.at("amount")}><Bar width={64} /></span>,
        currency: <span className={styles.currencyCell} style={places.at("currency")}><Bar width={30} /></span>,
        status: <span className={styles.state} style={places.at("status")}><Bar width={112} height={21} pill /></span>,
        arrival: <span className={styles.arrival} style={places.at("arrival")}><Bar width={72} /></span>,
      }}
      actions={<><div className={styles.rowAction}><div><Bar width={56} height={28} pill /></div></div><span className={styles.trashSlot} /></>}
    />
  </li>;
}

export default function ReceptionArrivalRow({ row, rowKey, arrived, panel, openPanel, preferences, selectable, checkable, checked, unseen, onCheck, onDelete }: { onDelete?: () => void; row: ReceptionRow; rowKey: string; arrived: boolean; selectable: boolean; checkable: boolean; checked: boolean; unseen: boolean; onCheck: () => void; panel: BusinessPanelState; openPanel: (panel: BusinessPanelState) => void; preferences: ReceptionPreferences }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const word = (key: string) => t(`business.reception_preview.${key}`);
  const receipt = row.kind === "receipt" ? row.receipt : null;
  const target = receptionTarget(row);
  const open = () => openPanel(target);
  const title = receptionDocumentTitle(row, { untitled: t("business.document_delete.unnamed"), pending: word("intake_pending"), exception: word("intake_exception"), text: word("text_intake") });
  const places = receptionPlaces(preferences);
  const has = places.has;
  const money = receipt && has("amount") ? formatMoney(receipt.amount, receipt.currency, locale) : null;
  const sentBy = receptionSentBy(row);
  const sender = sentBy ? sentByName(t, sentBy) : null;
  const SourceIcon = CHANNEL_ICON[row.source];
  const selected = isOpenRecord(panel, target);
  const [titleRef, titleCut] = useCutOff<HTMLSpanElement>(title);
  const arrival = has("arrival") ? <time dateTime={row.receivedAt} title={formatDate(new Date(row.receivedAt), locale, { dateStyle: "medium", timeStyle: "short" })}>{formatRelativeTime(row.receivedAt, locale)}</time> : null;
  const identity = <button type="button" onClick={open} className={styles.identity}>
    <span className={styles.documentText}>{unseen ? <span className={styles.unseenDot} aria-hidden="true" /> : null}<span ref={titleRef} className={styles.title}>{unseen ? <span className="sr-only">{word("unseen")}: </span> : null}{row.kind === "note" ? <ChatCircle className={styles.noteIcon} size={15} aria-hidden="true" /> : null}{title}</span>{money ? <span className={`${styles.mobileMoney} cuadrao-amount`}>{money}</span> : null}</span>
  </button>;
  const channel = (cell?: CellProps) => has("source") ? <span className={styles.channel} {...cell}><SourceIcon size={15} aria-hidden="true" />{t(receptionChannelKey(row.source))}</span> : null;
  const from = (cell?: CellProps) => !has("sender") ? null : sender ? <ReceptionCutText text={sender} className={styles.sender} data-known="true" {...cell} /> : <span className={styles.sender} data-known="false" {...cell}>{t("business.dossier.row.no_data")}</span>;
  // Below 940px Canal, Enviado por and the phone's arrival share one cell, in the order they read there. A wide table hides it and draws each at its own place.
  const origin = <span className={styles.source} style={places.shared} data-info={has("source") || has("sender")} data-testid="reception-source">
    {from()}{channel()}
    {arrival ? <span className={styles.mobileArrival}>{arrival}</span> : null}
  </span>;
  const cells: Record<ReceptionColumnKey, ReactNode> = {
    file: <span className={styles.fileCell} style={places.at("file")} data-file={!!receipt || row.kind === "note"}>{receipt ? <ReceptionOriginal receipt={receipt} /> : row.kind === "note" ? <Unknown meaning={word("without_file")} /> : <Unknown meaning={word("no_file")} />}</span>,
    source: channel({ style: places.at("source"), "data-testid": "reception-channel" }),
    sender: from({ style: places.at("sender"), "data-testid": "reception-sender" }),
    amount: <span data-testid="reception-amount" style={places.at("amount")} className={`${styles.amountCell} cuadrao-amount`}>{receipt?.amount != null && receipt.currency ? formatAmount(receipt.amount, receipt.currency, locale) : <Unknown />}</span>,
    currency: <span data-testid="reception-currency" style={places.at("currency")} className={styles.currencyCell}>{receipt?.currency ? currencySymbol(receipt.currency) : <Unknown />}</span>,
    status: <ReceptionStatus row={row} style={places.at("status")} />,
    arrival: <span className={styles.arrival} style={places.at("arrival")}>{arrival}</span>,
  };
  return <li className={styles.row} data-list-row={rowKey} data-arrived={arrived} data-selected={selected} data-checked={checkable && checked} data-unseen={unseen} aria-current={selected ? "true" : undefined} data-testid="reception-row" data-kind={row.kind} onClick={event => { if (!(event.target as HTMLElement).closest("button,input,label,a")) open(); }}>
    <RowPlaces places={places} cells={cells} origin={origin}
      box={!selectable ? null : checkable ? <label className={styles.checkbox}><input type="checkbox" checked={checked} onChange={onCheck} aria-label={t("business.reception_preview.select_document", { name: title })} /></label> : <span className={styles.checkbox} />}
      identity={titleCut ? <Tooltip content={title} side="top">{identity}</Tooltip> : identity}
      actions={<><button type="button" className={`${styles.rowAction} rounded-full`} onClick={open}><span>{word("placeholder.open")}</span></button>{onDelete ? <Tooltip content={t("business.document_delete.delete")} side="top"><button type="button" className={`${styles.trashAction} rounded-full`} onClick={onDelete} aria-label={t("business.document_delete.label", { name: title })}><Trash2 size={17} aria-hidden="true" /></button></Tooltip> : <span className={styles.trashSlot} aria-hidden="true" />}</>} />
  </li>;
}
