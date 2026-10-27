"use client";

import { useState } from "react";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { LockKeyhole, Search, SlidersHorizontal, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import RecordsPreviewPopover from "../transacciones/RecordsPreviewPopover";
import { DENSITIES, type Density } from "../transacciones/table-density";
import controlStyles from "../transacciones/records-filter-preview.module.css";
import styles from "./reception.module.css";

export type ReceptionPreferences = { density: Density; source: boolean; sender: boolean; arrival: boolean; amount: boolean; currency: boolean };
export const defaultReceptionPreferences = (): ReceptionPreferences => ({ density: "amplio", source: true, sender: true, arrival: true, amount: false, currency: false });

export function ReceptionSearch({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const { t } = useTranslation();
  return <label className={styles.search}><Search className="pointer-events-none absolute left-3.5 top-3.5 h-4 w-4 text-[#56635e] dark:text-white/45" aria-hidden="true" /><input className="h-11 w-full rounded-full border border-[#DCE0DA] bg-white pl-10 pr-10 text-[16px] text-[#172b26] placeholder:text-[#7d8a84] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--cuadrao-green)] dark:border-white/15 dark:bg-[#1f2225] dark:text-white dark:placeholder:text-white/45" type="search" aria-label={t("business.reception_preview.search")} placeholder={t("business.reception_preview.search")} value={value} onChange={event => onChange(event.target.value)} />{value ? <button type="button" onClick={() => onChange("")} aria-label={t("business.reception_preview.clear")}><X size={16} /></button> : null}</label>;
}

export function ReceptionSettings({ value, onChange }: { value: ReceptionPreferences; onChange: (value: ReceptionPreferences) => void }) {
  const { t } = useTranslation();
  return <RecordsPreviewPopover iconOnly label={t("business.transactions.density.options")} icon={<SlidersHorizontal size={18} aria-hidden="true" />} width={440}>
    {() => <ReceptionSettingsBody value={value} onChange={onChange} />}
  </RecordsPreviewPopover>;
}

function ReceptionSettingsBody({ value, onChange }: { value: ReceptionPreferences; onChange: (value: ReceptionPreferences) => void }) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<"columns" | "height">("columns");
  const word = (key: string) => t(`business.transactions.layout.settings.${key}`);
  const label = (key: string) => t(key === "currency" ? "business.transactions.columns.moneda" : `business.reception_preview.${key}`);
  return <div className={controlStyles.settings}>
    <SegmentedControl label={t("business.transactions.density.options")} value={tab} onChange={setTab} segments={(["columns", "height"] as const).map(key => ({ key, label: key === "columns" ? t("business.reception_preview.visible_information") : word(key) }))} fill />
    {tab === "columns" ? <section aria-label={t("business.reception_preview.visible_information")}>
      <ul className={controlStyles.columnList}>{(["document", "file", "source", "sender", "amount", "currency", "status", "arrival", "next_action"] as const).map(key => <li key={key} className={controlStyles.columnRow}>
        {key === "source" || key === "sender" || key === "arrival" || key === "amount" || key === "currency" ? <label className={controlStyles.choice}><input type="checkbox" checked={value[key]} onChange={() => onChange({ ...value, [key]: !value[key] })} /><span>{label(key)}</span></label> : <div className={controlStyles.requiredColumn}><LockKeyhole size={16} aria-hidden="true" /><span>{label(key)}<small className={controlStyles.required}>{word(key === "document" ? "fixed" : "required")}</small></span></div>}
      </li>)}</ul>
    </section> : <section aria-label={word("height")}>{DENSITIES.map(density => <label className={controlStyles.choice} key={density}><input type="radio" name="reception-density" checked={value.density === density} onChange={() => onChange({ ...value, density })} /><span>{t(`business.transactions.density.${density}`)}</span></label>)}</section>}
    <div className={controlStyles.settingsFooter}><button type="button" className={controlStyles.clear} onClick={() => onChange(defaultReceptionPreferences())}>{word("restore")}</button></div>
  </div>;
}

