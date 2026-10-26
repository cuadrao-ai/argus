"use client";

import { useState } from "react";
import { useTransaccionesWords } from "./transacciones-words";
import controls from "./records-filter-preview.module.css";
import styles from "./records-results-preview.module.css";

export default function RecordsSummaryEditor({ initial, apply, close, phone }: { initial: boolean; apply: (value: boolean) => void; close: () => void; phone: boolean }) {
  const { t } = useTransaccionesWords();
  const [draft, setDraft] = useState(initial);
  return <>
    <div className={styles.customizer}>
      <label className={controls.choice} data-summary-setting><input type="checkbox" checked={draft} onChange={(event) => setDraft(event.target.checked)} /><span>{t("business.transactions.layout.results.show")}</span></label>
      <p className={controls.hint}>{t("business.transactions.layout.results.show_hint")}</p>
    </div>
    <div className={`${controls.footer} ${phone ? controls.phoneFooter : ""}`}><button type="button" className={controls.clear} onClick={() => setDraft(true)}>{t("business.transactions.layout.results.restore")}</button><button type="button" className={controls.apply} onClick={() => { apply(draft); close(); }}>{t("business.transactions.layout.filters.apply")}</button></div>
  </>;
}
