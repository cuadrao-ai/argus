"use client";

import { Search, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import RecordsSettingsPreview from "../transacciones/RecordsSettingsPreview";
import { defaultReceptionPreferences, receptionLayout, type ReceptionPreferences } from "./reception-columns";
import type { ReceptionView } from "./reception-model";
import styles from "./reception.module.css";

export function ReceptionSearch({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const { t } = useTranslation();
  return <label className={styles.search}><Search className="pointer-events-none absolute left-3.5 top-3.5 h-4 w-4 text-[#56635e] dark:text-white/45" aria-hidden="true" /><input className="h-11 w-full rounded-full border border-[#DCE0DA] bg-white pl-10 pr-10 text-[16px] text-[#172b26] placeholder:text-[#7d8a84] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--cuadrao-green)] dark:border-white/15 dark:bg-[#1f2225] dark:text-white dark:placeholder:text-white/45" type="search" aria-label={t("business.reception_preview.search")} placeholder={t("business.reception_preview.search")} value={value} onChange={event => onChange(event.target.value)} />{value ? <button type="button" onClick={() => onChange("")} aria-label={t("business.reception_preview.clear")}><X size={16} /></button> : null}</label>;
}

export function ReceptionSettings({ value, view, onChange }: { value: ReceptionPreferences; view: ReceptionView; onChange: (value: ReceptionPreferences) => void }) {
  return <RecordsSettingsPreview cards value={receptionLayout(value, view)} onChange={({ order, hidden, density }) => onChange({ order, hidden, density })} onRestore={() => onChange(defaultReceptionPreferences())} />;
}
