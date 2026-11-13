"use client";

import { useTranslation } from "react-i18next";
import { formatRelativeTime } from "../business-format";
import { quietButtonClass } from "../business-ui";
import { RestoreDocumentButton } from "../DocumentDeleteControls";
import type { BusinessPanelState } from "../BusinessWorkspace";
import { receptionTarget, type ReceptionRow } from "./reception-model";
import styles from "./reception.module.css";

export function DeletedColumns() {
  const { t } = useTranslation();
  return <div className={styles.deletedColumns}>{["content", "previous", "actor", "when"].map(key => <span key={key}>{t(`business.document_delete.columns.${key}`)}</span>)}<span className="sr-only">{t("business.document_delete.actions")}</span></div>;
}

export default function ReceptionDeletedRow({ row, title, openPanel }: { row: ReceptionRow; title: string; openPanel: (panel: BusinessPanelState) => void }) {
  const { t, i18n } = useTranslation();
  if (row.kind === "email") return null;
  const document = row.kind === "receipt" ? row.receipt : row.note;
  const deletion = document.deleted;
  if (!deletion) return null;
  const target = receptionTarget(row);
  return <li className={styles.deletedRow} data-testid="deleted-document-row">
    <span className={styles.deletedName}>{title}</span>
    <span className={styles.deletedMeta}>{t(`business.document_delete.previous.${deletion.previous_state.group}`)}</span>
    <span className={styles.deletedMeta}>{deletion.actor.display_name}</span>
    <time className={styles.deletedMeta} dateTime={deletion.at}>{formatRelativeTime(deletion.at, i18n.resolvedLanguage ?? i18n.language)}</time>
    <span className={styles.deletedActions}><button type="button" className={quietButtonClass} onClick={() => openPanel(target)}>{t("business.document_delete.view")}</button>{document.restore_available ? <RestoreDocumentButton id={row.id} target={target} /> : null}</span>
  </li>;
}
