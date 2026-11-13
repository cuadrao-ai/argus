"use client";

import { useTranslation } from "react-i18next";
import { dueDistance } from "@/lib/business-month-close";
import { formatRelativeTime, todayIso } from "../business-format";
import { quietButtonClass } from "../business-ui";
import { PurgeDocumentButton, RestoreDocumentButton } from "../DocumentDeleteControls";
import type { BusinessPanelState } from "../BusinessWorkspace";
import { receptionTarget, rowDeleteTarget, type ReceptionRow } from "./reception-model";
import styles from "./reception.module.css";

/** Calendar days until the server's purge, 0 on its day and after. */
export function purgeDays(purgeAt: string, now = new Date()): number {
  const distance = dueDistance(todayIso(new Date(purgeAt)), todayIso(now));
  return distance?.direction === "future" ? distance.days : 0;
}

export function DeletedColumns() {
  const { t } = useTranslation();
  return <div className={styles.deletedColumns}>{["content", "previous", "actor", "purge"].map(key => <span key={key} className={key === "previous" ? styles.deletedPrevious : undefined}>{t(`business.document_delete.columns.${key}`)}</span>)}<span className="sr-only">{t("business.document_delete.actions")}</span></div>;
}

export default function ReceptionDeletedRow({ row, title, openPanel }: { row: ReceptionRow; title: string; openPanel: (panel: BusinessPanelState) => void }) {
  const { t, i18n } = useTranslation();
  if (row.kind === "email") return null;
  const document = row.kind === "receipt" ? row.receipt : row.note;
  const deletion = document.deleted;
  if (!deletion) return null;
  const target = receptionTarget(row);
  const days = purgeDays(deletion.purge_at);
  return <li className={styles.deletedRow} data-testid="deleted-document-row">
    <span className={styles.deletedName}>{title}</span>
    <span className={`${styles.deletedMeta} ${styles.deletedPrevious}`}>{t(`business.document_delete.previous.${deletion.previous_state.group}`)}</span>
    <span className={styles.deletedMeta}>{deletion.actor.display_name} · <time dateTime={deletion.at}>{formatRelativeTime(deletion.at, i18n.resolvedLanguage ?? i18n.language)}</time></span>
    <time className={styles.deletedMeta} dateTime={deletion.purge_at} data-testid="purge-countdown"><span className={styles.purgeLead}>{t("business.document_delete.columns.purge")} </span>{days > 0 ? t("business.document_delete.purge_in", { count: days }) : t("business.document_delete.purge_today")}</time>
    <span className={styles.deletedActions}>{document.restore_available ? <span className={styles.purgeAction}><PurgeDocumentButton target={rowDeleteTarget(row, "", title)} /></span> : null}<button type="button" className={quietButtonClass} onClick={() => openPanel(target)}>{t("business.document_delete.view")}</button>{document.restore_available ? <RestoreDocumentButton id={row.id} target={target} /> : null}</span>
  </li>;
}
