"use client";

import { useEffect, useRef, useState } from "react";
import { Bookmark } from "lucide-react";
import type { Period } from "../business-format";
import type { RecordsFilter } from "./RecordsToolbar";
import type { PreviewFilters } from "./records-filter-preview-model";
import RecordsPreviewPopover from "./RecordsPreviewPopover";
import { useTransaccionesWords } from "./transacciones-words";
import styles from "./records-filter-preview.module.css";

export type RecordsViewSelection = { record: RecordsFilter; period: Period; filters: PreviewFilters };
export type SavedRecordsView = { name: string; selection: RecordsViewSelection };

export function RecordsViewsPreview({ views, select, save }: { views: SavedRecordsView[]; select: (selection: RecordsViewSelection) => void; save: (name: string) => void }) {
  const { t } = useTransaccionesWords();
  return <RecordsPreviewPopover label={t("business.transactions.layout.views.title")} icon={<Bookmark size={17} aria-hidden="true" />} width={340}>
    {(close) => <ViewsMenu views={views} select={select} save={save} close={close} />}
  </RecordsPreviewPopover>;
}

function ViewsMenu({ views, select, save, close }: { views: SavedRecordsView[]; select: (selection: RecordsViewSelection) => void; save: (name: string) => void; close: () => void }) {
  const { t } = useTransaccionesWords();
  const [saving, setSaving] = useState(false);
  const word = (key: string) => t(`business.transactions.layout.views.${key}`);
  if (saving) return <SaveViewForm names={views.map((view) => view.name)} save={save} close={close} />;
  return <>
    <div className={styles.viewsList}>
      {views.length ? views.map((view) => <button type="button" className={styles.group} key={view.name} onClick={() => { select(structuredClone(view.selection)); close(); }}>{view.name}</button>) : <p className={styles.hint}>{word("empty")}</p>}
    </div>
    <div className={styles.footer}><button type="button" className={styles.group} onClick={() => setSaving(true)}><Bookmark size={17} aria-hidden="true" />{word("save")}</button></div>
  </>;
}

function SaveViewForm({ names, save, close }: { names: string[]; save: (name: string) => void; close: () => void }) {
  const { t } = useTransaccionesWords();
  const [name, setName] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { input.current?.focus(); }, []);
  const word = (key: string) => t(`business.transactions.layout.views.${key}`);
  const duplicate = names.some((existing) => existing.toLocaleLowerCase() === name.trim().toLocaleLowerCase());
  return <form onSubmit={(event) => { event.preventDefault(); if (name.trim() && !duplicate) { save(name.trim()); close(); } }}>
    <div className={styles.editor}><label className={styles.field}><span>{word("name")}</span><input ref={input} className={styles.input} value={name} onChange={(event) => setName(event.target.value)} maxLength={60} placeholder={word("placeholder")} required /></label>{duplicate ? <p className={styles.error} role="alert">{word("duplicate")}</p> : null}</div>
    <div className={styles.footer}><span /><button type="submit" className={styles.apply} disabled={!name.trim() || duplicate}>{word("save")}</button></div>
  </form>;
}
