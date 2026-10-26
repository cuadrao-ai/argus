"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Bookmark } from "lucide-react";
import type { RecordsViewPreferences } from "./records-view-preferences";
import type { Period } from "../business-format";
import type { RecordsFilter } from "./RecordsToolbar";
import type { PreviewFilters } from "./records-filter-preview-model";
import RecordsPreviewPopover from "./RecordsPreviewPopover";
import { useTransaccionesWords } from "./transacciones-words";
import styles from "./records-filter-preview.module.css";

export type RecordsViewSelection = { record: RecordsFilter; period: Period; filters: PreviewFilters; preferences?: RecordsViewPreferences };
export type SavedRecordsView = { name: string; selection: RecordsViewSelection };

export type ConnectedReportViews = { items: { id: string; name: string }[]; select: (id: string) => void; save: (name: string) => Promise<boolean>; update: (id: string, name: string) => Promise<boolean>; remove: (id: string) => void; busy: boolean; notice: ReactNode };

export function RecordsViewsPreview({ views, select, save, connected }: { connected?: ConnectedReportViews; views: SavedRecordsView[]; select: (selection: RecordsViewSelection) => void; save: (name: string) => void }) {
  const { t } = useTransaccionesWords();
  return <RecordsPreviewPopover label={t("business.transactions.layout.views.title")} icon={<Bookmark size={17} aria-hidden="true" />} width={340}>
    {(close) => connected ? <ConnectedViewsMenu connected={connected} close={close} /> : <ViewsMenu views={views} select={select} save={save} close={close} />}
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

function ConnectedViewsMenu({ connected, close }: { connected: ConnectedReportViews; close: () => void }) {
  const { t } = useTransaccionesWords();
  const [editing, setEditing] = useState<{ id?: string; name: string } | null>(null);
  const [name, setName] = useState("");
  if (editing) return <form onSubmit={(event) => { event.preventDefault(); if (!name.trim() || connected.busy) return; void (editing.id ? connected.update(editing.id, name.trim()) : connected.save(name.trim())).then((saved) => { if (saved) close(); }); }}>
    <div className={styles.editor}><label className={styles.field}><span>{t("business.transactions.layout.views.name")}</span><input autoFocus className={styles.input} value={name} onChange={(event) => setName(event.target.value)} maxLength={120} required /></label>{connected.notice}</div>
    <div className={styles.footer}><button type="button" className={styles.clear} onClick={() => setEditing(null)}>{t("common.back")}</button><button className={styles.apply} type="submit" disabled={!name.trim() || connected.busy}>{t("common.save")}</button></div>
  </form>;
  return <><div className={styles.viewsList}>{connected.notice}{connected.items.length ? connected.items.map((view) => <div key={view.id}>
    <button type="button" className={styles.group} onClick={() => { connected.select(view.id); close(); }}>{view.name}</button>
    <div className={styles.footer}><button type="button" disabled={connected.busy} className={styles.clear} onClick={() => { setEditing(view); setName(view.name); }}>{t("common.rename")}</button><button type="button" disabled={connected.busy} className={styles.clear} onClick={() => connected.remove(view.id)}>{t("common.delete")}</button></div>
  </div>) : <p className={styles.hint}>{t("business.transactions.layout.views.empty")}</p>}</div><div className={styles.footer}><button type="button" disabled={connected.busy} className={styles.group} onClick={() => { setEditing({ name: "" }); setName(""); }}>{t("business.transactions.layout.views.save")}</button></div></>;
}
