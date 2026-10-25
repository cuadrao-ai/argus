"use client";

import { useState } from "react";
import { Bookmark, Download } from "lucide-react";
import type { Period } from "../business-format";
import type { RecordsFilter } from "./RecordsToolbar";
import type { PreviewFilters } from "./records-filter-preview-model";
import RecordsPreviewPopover from "./RecordsPreviewPopover";
import { useTransaccionesWords } from "./transacciones-words";
import styles from "./records-filter-preview.module.css";

export type RecordsViewSelection = { record: RecordsFilter; period: Period; filters: PreviewFilters };
export type SavedRecordsView = { name: string; selection: RecordsViewSelection };

export function RecordsViewsPreview({ views, select }: { views: SavedRecordsView[]; select: (selection: RecordsViewSelection) => void }) {
  const { t } = useTransaccionesWords();
  const word = (key: string) => t(`business.transactions.layout.views.${key}`);
  return <RecordsPreviewPopover label={word("title")} icon={<Bookmark size={17} aria-hidden="true" />} width={300}>
    {(close) => <div className={styles.viewsList}>
      {views.length ? views.map((view) => <button type="button" className={styles.group} key={view.name} onClick={() => { select(structuredClone(view.selection)); close(); }}>{view.name}</button>) : <p className={styles.hint}>{word("empty")}</p>}
    </div>}
  </RecordsPreviewPopover>;
}

function SaveViewForm({ names, save, close }: { names: string[]; save: (name: string) => void; close: () => void }) {
  const { t } = useTransaccionesWords();
  const [name, setName] = useState("");
  const word = (key: string) => t(`business.transactions.layout.views.${key}`);
  const duplicate = names.some((existing) => existing.toLocaleLowerCase() === name.trim().toLocaleLowerCase());
  return <form onSubmit={(event) => { event.preventDefault(); if (name.trim() && !duplicate) { save(name.trim()); close(); } }}>
    <div className={styles.editor}><label className={styles.field}><span>{word("name")}</span><input className={styles.input} value={name} onChange={(event) => setName(event.target.value)} maxLength={60} placeholder={word("placeholder")} required /></label>{duplicate ? <p className={styles.error} role="alert">{word("duplicate")}</p> : null}</div>
    <div className={styles.footer}><span /><button type="submit" className={styles.apply} disabled={!name.trim() || duplicate}>{word("save")}</button></div>
  </form>;
}

export function RecordsViewActionsPreview({ names, save }: { names: string[]; save: (name: string) => void }) {
  const { t } = useTransaccionesWords();
  return <div className={styles.viewActions}>
    <RecordsPreviewPopover label={t("business.transactions.layout.views.save")} icon={<Bookmark size={16} aria-hidden="true" />} width={340}>
      {(close) => <SaveViewForm names={names} save={save} close={close} />}
    </RecordsPreviewPopover>
    <button type="button" disabled className={styles.trigger}><Download size={16} aria-hidden="true" />{t("business.transactions.layout.views.export")}</button>
  </div>;
}
