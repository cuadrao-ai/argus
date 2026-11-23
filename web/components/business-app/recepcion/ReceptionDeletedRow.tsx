"use client";

import { useTranslation } from "react-i18next";
import { personName } from "@/lib/person-name";
import { dueDistance } from "@/lib/business-month-close";
import { formatRelativeTime, formatTimestamp, todayIso } from "../business-format";
import { PurgeDocumentButton, RestoreDocumentButton } from "../DocumentDeleteControls";
import type { BusinessPanelState } from "../BusinessWorkspace";
import ReceptionCutText from "./ReceptionCutText";
import { receptionTarget, rowDeleteTarget, type ReceptionRow } from "./reception-model";
import styles from "./reception.module.css";

export function DeletedColumns() {
  const { t } = useTranslation();
  return <div className={styles.deletedColumns} data-testid="deleted-columns">{["content", "previous", "actor", "purge"].map(key => <span key={key} className={key === "previous" ? styles.deletedPrevious : undefined}>{t(`business.document_delete.columns.${key}`)}</span>)}<span className="sr-only">{t("business.document_delete.actions")}</span></div>;
}

export default function ReceptionDeletedRow({ row, title, openPanel }: { row: ReceptionRow; title: string; openPanel: (panel: BusinessPanelState) => void }) {
  const { t, i18n } = useTranslation();
  if (row.kind === "email") return null;
  const document = row.kind === "receipt" ? row.receipt : row.note;
  const deletion = document.deleted;
  if (!deletion) return null;
  const target = receptionTarget(row);
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const distance = dueDistance(todayIso(new Date(deletion.purge_at)), todayIso());
  const lastDay = distance?.direction === "today";
  const deadline = distance?.direction === "future" ? t("business.document_delete.purge_in", { count: distance.days })
    : lastDay ? t("business.document_delete.purge_today")
    : t("business.document_delete.purge_at", { date: formatTimestamp(deletion.purge_at, locale) });
  return <li className={styles.deletedRow} data-testid="deleted-document-row">
    <ReceptionCutText text={title} className={styles.deletedName} />
    <span className={`${styles.deletedMeta} ${styles.deletedPrevious}`}>{t(`business.document_delete.previous.${deletion.previous_state.group}`)}</span>
    <span className={styles.deletedActor} data-testid="deleted-actor"><ReceptionCutText text={personName(t, deletion.actor)} className={styles.deletedActorName} /><time className={styles.deletedMeta} dateTime={deletion.at}>{formatRelativeTime(deletion.at, locale)}</time></span>
    <time className={styles.deletedMeta} dateTime={deletion.purge_at} data-testid="purge-countdown" data-last-day={lastDay}><span className={styles.purgeLead}>{t("business.document_delete.columns.purge")} </span>{deadline}</time>
    <span className={styles.deletedActions}><button type="button" className={styles.viewAction} onClick={() => openPanel(target)}>{t("business.document_delete.view")}</button>{document.restore_available ? <RestoreDocumentButton id={row.id} target={target} className={styles.restoreAction} /> : null}{document.restore_available ? <PurgeDocumentButton target={rowDeleteTarget(row, "", title)} className={styles.trashAction} /> : null}</span>
  </li>;
}
