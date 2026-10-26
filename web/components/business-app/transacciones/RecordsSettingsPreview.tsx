"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { GripVertical, LockKeyhole, SlidersHorizontal } from "lucide-react";
import RecordsPreviewPopover from "./RecordsPreviewPopover";
import { DENSITIES } from "./table-density";
import type { ColumnKey } from "./TransaccionesTable";
import { defaultRecordsPreferences, moveRecordsColumn, requiredColumn, toggleRecordsColumn, type RecordsViewPreferences } from "./records-view-preferences";
import { useTransaccionesWords } from "./transacciones-words";
import styles from "./records-filter-preview.module.css";

export default function RecordsSettingsPreview({ value, onChange }: { value: RecordsViewPreferences; onChange: (value: RecordsViewPreferences) => void }) {
  const { t } = useTransaccionesWords();
  const cancelMove = useRef<(() => boolean) | null>(null);
  const registerCancel = useCallback((handler: (() => boolean) | null) => { cancelMove.current = handler; }, []);
  return <RecordsPreviewPopover beforeEscape={() => cancelMove.current?.() ?? false} iconOnly label={t("business.transactions.density.options")} icon={<SlidersHorizontal size={18} aria-hidden="true" />} width={340}>
    {() => <Settings value={value} onChange={onChange} registerCancel={registerCancel} />}
  </RecordsPreviewPopover>;
}
function Settings({ value, onChange, registerCancel }: { registerCancel: (handler: (() => boolean) | null) => void; value: RecordsViewPreferences; onChange: (value: RecordsViewPreferences) => void }) {
  const { t } = useTransaccionesWords();
  const word = (key: string) => t(`business.transactions.layout.settings.${key}`);
  const label = (key: ColumnKey) => t(`business.transactions.columns.${key}`, { currency: "" }).trim();
  const [tab, setTab] = useState<"columns" | "height">("columns");
  const [grabbed, setGrabbed] = useState<ColumnKey | null>(null);
  const before = useRef<ColumnKey[] | null>(null);
  const [dragging, setDragging] = useState<ColumnKey | null>(null);
  const [dropTarget, setDropTarget] = useState<ColumnKey | null>(null);
  const [message, setMessage] = useState("");
  const hintId = useId();
  useEffect(() => {
    registerCancel(() => {
      if (!grabbed) return false;
      if (before.current) onChange({ ...value, order: before.current });
      setGrabbed(null); setMessage(t("business.transactions.layout.settings.cancelled"));
      return true;
    });
    return () => registerCancel(null);
  }, [registerCancel, grabbed, onChange, t, value]);
  const move = (key: ColumnKey, target: number) => {
    const next = moveRecordsColumn(value, key, target); onChange(next);
    setMessage(t("business.transactions.layout.settings.position", { name: label(key), position: next.order.indexOf(key) + 1, count: next.order.length }));
  };
  return <div className={styles.settings}>
    <div className={styles.settingsTabs} role="tablist" aria-label={t("business.transactions.density.options")} onKeyDown={(event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === "Home" ? "columns" : event.key === "End" ? "height" : tab === "columns" ? "height" : "columns";
      setTab(next); event.currentTarget.querySelectorAll<HTMLButtonElement>("button")[next === "columns" ? 0 : 1]?.focus();
    }}>
      {(["columns", "height"] as const).map((key) => <button type="button" role="tab" id={`${hintId}-${key}-tab`} aria-controls={`${hintId}-${key}-panel`} tabIndex={tab === key ? 0 : -1} aria-selected={tab === key} key={key} className={styles.group} onClick={() => setTab(key)}>{word(key)}</button>)}
    </div>
    {tab === "columns" ? <section role="tabpanel" id={`${hintId}-columns-panel`} aria-labelledby={`${hintId}-columns-tab`}>
      <p id={hintId} className={styles.hint}>{word("instructions")}</p>
      <ul className={styles.columnList}>{value.order.map((key, index) => <li key={key} data-column-setting={key} className={`${styles.columnRow} ${dropTarget === key ? (dragging && value.order.indexOf(dragging) < index ? styles.dropAfter : styles.dropBefore) : ""}`} onDragOver={(event) => { if (dragging && key !== "contraparte") { event.preventDefault(); setDropTarget(dragging === key ? null : key); } }} onDrop={(event) => { event.preventDefault(); if (dragging && key !== "contraparte") move(dragging, index); setDragging(null); setDropTarget(null); }}>
        <label className={styles.choice}><input type="checkbox" checked={requiredColumn(key) || !value.hidden.includes(key)} disabled={requiredColumn(key)} onChange={() => onChange(toggleRecordsColumn(value, key))} /><span>{label(key)}{requiredColumn(key) ? <small className={styles.required}>{word(key === "contraparte" ? "fixed" : "required")}</small> : null}</span></label>
        {key === "contraparte" ? <span className={styles.iconButton}><LockKeyhole size={15} aria-hidden="true" /></span> : <button type="button" className={styles.grip} draggable aria-label={t("business.transactions.layout.settings.move", { name: label(key) })} aria-describedby={hintId} aria-pressed={grabbed === key} onDragStart={(event) => { setDragging(key); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", key); }} onDragEnd={() => { setDragging(null); setDropTarget(null); }} onKeyDown={(event) => {
          if (event.key === " ") { event.preventDefault(); if (grabbed === key) { setGrabbed(null); before.current = null; setMessage(word("dropped")); } else { before.current = value.order; setGrabbed(key); setMessage(word("grabbed")); } }
          else if (grabbed === key && (event.key === "ArrowUp" || event.key === "ArrowDown")) { event.preventDefault(); move(key, index + (event.key === "ArrowUp" ? -1 : 1)); }
          else if (grabbed === key && event.key === "Escape") { event.preventDefault(); event.stopPropagation(); if (before.current) onChange({ ...value, order: before.current }); setGrabbed(null); setMessage(word("cancelled")); }
        }}><GripVertical size={18} aria-hidden="true" /></button>}
      </li>)}</ul>
      <span className={styles.srOnly} role="status" aria-live="polite">{message}</span>
    </section> : <section role="tabpanel" id={`${hintId}-height-panel`} aria-labelledby={`${hintId}-height-tab`}>{DENSITIES.map((density) => <label className={styles.choice} key={density}><input type="radio" name="records-preview-density" checked={value.density === density} onChange={() => onChange({ ...value, density })} /><span>{t(`business.transactions.density.${density}`)}</span></label>)}</section>}
    <div className={styles.settingsFooter}><button type="button" className={styles.clear} onClick={() => { before.current = null; setGrabbed(null); setDragging(null); setDropTarget(null); onChange(defaultRecordsPreferences()); }}>{word("restore")}</button></div>
  </div>;
}
