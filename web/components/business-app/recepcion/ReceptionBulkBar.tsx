"use client";

import { Archive, Eye, EyeOff, RotateCcw, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OrganizationAction } from "./reception-organization-preview";
import styles from "./reception.module.css";

export default function ReceptionBulkBar({ count, archived, canOrganize, apply, clear }: { count: number; archived: boolean; canOrganize: boolean; apply: (action: OrganizationAction) => void; clear: () => void }) {
  const { t } = useTranslation();
  const word = (key: string) => t(`business.reception_preview.${key}`);
  const ArchiveIcon = archived ? RotateCcw : Archive;
  return <div className={styles.bulkBar} role="region" aria-label={word("bulk_actions")}>
    <span className={styles.selectedCount} title={t("business.reception_preview.selected_page", { count })}>{t("business.reception_preview.selected", { count })}</span><span aria-hidden="true">·</span>
    <button type="button" disabled={!canOrganize} aria-label={word(archived ? "restore" : "archive")} title={word(canOrganize ? "archive_scope" : "archive_permission")} onClick={() => apply(archived ? "restore" : "archive")}><ArchiveIcon size={16} aria-hidden="true" /><span className={styles.bulkArchiveLabel}>{word(archived ? "restore" : "archive")}</span></button>
    <button type="button" title={word("seen_scope")} aria-label={word("mark_seen")} onClick={() => apply("seen")}><Eye size={16} aria-hidden="true" /><span className={styles.bulkSeenLabel}>{word("seen")}</span></button>
    <button type="button" title={word("seen_scope")} aria-label={word("mark_unseen")} onClick={() => apply("unseen")}><EyeOff size={16} aria-hidden="true" /><span className={styles.bulkSeenLabel}>{word("unseen")}</span></button>
    <button type="button" aria-label={word("clear_selection")} title={word("clear_selection")} onClick={clear}><X size={16} aria-hidden="true" /></button>
  </div>;
}
