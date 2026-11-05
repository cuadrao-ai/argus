"use client";

import { Check, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import styles from "./reception.module.css";

export default function ReceptionBulkBar({ count, approve, clear }: { count: number; approve: () => void; clear: () => void }) {
  const { t } = useTranslation();
  const word = (key: string) => t(`business.reception_preview.${key}`);
  return <div className={styles.bulkBar} role="region" aria-label={word("placeholder.bulk_actions")}>
    <span className={styles.selectedCount}>{t("business.reception_preview.selected", { count })}</span><span aria-hidden="true">·</span>
    <button type="button" data-testid="reception-approve-selected" onClick={approve}><Check size={16} aria-hidden="true" />{t("business.dossier.approve_action")}</button>
    <button type="button" aria-label={word("clear_selection")} title={word("clear_selection")} onClick={clear}><X size={16} aria-hidden="true" /></button>
  </div>;
}
