"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { ArrowDown, ArrowUp, GripVertical, LockKeyhole, SlidersHorizontal } from "lucide-react";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import RecordsPreviewPopover from "./RecordsPreviewPopover";
import { DENSITIES } from "./table-density";
import { recordsColumnLabelKey, type RecordsColumnKey, moveRecordsColumn, purchaseOnlyColumn, requiredColumn, toggleRecordsColumn, type RecordsViewPreferences } from "./records-view-preferences";
import { useTransaccionesWords } from "./transacciones-words";
import styles from "./records-filter-preview.module.css";

export default function RecordsSettingsPreview({ value, onChange, onRestore, purchase = true }: { purchase?: boolean; value: RecordsViewPreferences; onChange: (value: RecordsViewPreferences) => void; onRestore: () => void }) {
  const { t } = useTransaccionesWords();
  const { isBelowDesktop: phone } = useResponsiveLayout();
  const cancelMove = useRef<(() => boolean) | null>(null);
  const registerCancel = useCallback((handler: (() => boolean) | null) => { cancelMove.current = handler; }, []);
  if (phone) return null;
  return <RecordsPreviewPopover beforeEscape={() => cancelMove.current?.() ?? false} iconOnly label={t("business.transactions.density.options")} icon={<SlidersHorizontal size={18} aria-hidden="true" />} width={440}>
    {() => <Settings purchase={purchase} value={value} onChange={onChange} onRestore={onRestore} registerCancel={registerCancel} />}
  </RecordsPreviewPopover>;
}
function Settings({ value, onChange, onRestore, registerCancel, purchase }: { purchase: boolean; registerCancel: (handler: (() => boolean) | null) => void; value: RecordsViewPreferences; onChange: (value: RecordsViewPreferences) => void; onRestore: () => void }) {
  const { t } = useTransaccionesWords();
  const word = (key: string) => t(`business.transactions.layout.settings.${key}`);
  const label = (key: RecordsColumnKey) => t(recordsColumnLabelKey(key), { currency: "" }).trim();
  const [tab, setTab] = useState<"columns" | "height">("columns");
  const [grabbed, setGrabbed] = useState<RecordsColumnKey | null>(null);
  const before = useRef<RecordsColumnKey[] | null>(null);
  const [dragging, setDragging] = useState<RecordsColumnKey | null>(null);
  const [dropTarget, setDropTarget] = useState<RecordsColumnKey | null>(null);
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
  const order = value.order.filter((key) => purchase || !purchaseOnlyColumn(key));
  const move = (key: RecordsColumnKey, target: number) => {
    const next = moveRecordsColumn(value, key, target); onChange(next);
    setMessage(t("business.transactions.layout.settings.position", { name: label(key), position: next.order.indexOf(key) + 1, count: next.order.length }));
  };
  return <div className={styles.settings}>
    <SegmentedControl label={t("business.transactions.density.options")} value={tab} onChange={setTab} segments={(["columns", "height"] as const).map((key) => ({ key, label: word(key) }))} fill />
    {tab === "columns" ? <section aria-label={word("columns")}>
      <p id={hintId} className={`${styles.hint} ${styles.settingsHint}`} data-picked-up={grabbed ? true : undefined}><span aria-hidden={grabbed ? true : undefined}>{word("instructions")}</span>{grabbed ? <span>{word("grabbed")}</span> : null}</p>
      <ul className={styles.columnList}>{order.map((key, index) => <li key={key} data-column-setting={key} data-picked-up={grabbed === key ? true : undefined} className={`${styles.columnRow} ${dropTarget === key ? (dragging && value.order.indexOf(dragging) < index ? styles.dropAfter : styles.dropBefore) : ""}`} onDragOver={(event) => { if (dragging && key !== "contraparte") { event.preventDefault(); setDropTarget(dragging === key ? null : key); } }} onDrop={(event) => { event.preventDefault(); if (dragging && key !== "contraparte") move(dragging, value.order.indexOf(key)); setDragging(null); setDropTarget(null); }}>
        {requiredColumn(key) ? <div className={styles.requiredColumn}><LockKeyhole size={16} aria-hidden="true" /><span>{label(key)}<small className={styles.required}>{word(key === "contraparte" ? "fixed" : "required")}</small></span></div> : <label className={styles.choice}><input type="checkbox" checked={!value.hidden.includes(key)} onChange={() => onChange(toggleRecordsColumn(value, key))} /><span>{label(key)}</span></label>}
        {key !== "contraparte" ? <>{([-1, 1] as const).map((step) => <button key={step} type="button" className={styles.grip} aria-label={t(`business.transactions.layout.settings.${step === -1 ? "move_up" : "move_down"}`, { name: label(key) })} disabled={step === -1 ? index <= 1 : index === order.length - 1} onClick={() => move(key, value.order.indexOf(order[index + step]))}>{step === -1 ? <ArrowUp size={16} aria-hidden="true" /> : <ArrowDown size={16} aria-hidden="true" />}</button>)}<button type="button" className={styles.grip} draggable onPointerDown={(event) => event.currentTarget.focus()} aria-label={t("business.transactions.layout.settings.move", { name: label(key) })} aria-describedby={hintId} aria-pressed={grabbed === key} onDragStart={(event) => { setDragging(key); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", key); }} onDragEnd={() => { setDragging(null); setDropTarget(null); }} onKeyDown={(event) => {
          if (event.key === " ") { event.preventDefault(); if (event.repeat) return; if (grabbed === key) { setGrabbed(null); before.current = null; setMessage(word("dropped")); } else { before.current = value.order; setGrabbed(key); setMessage(word("grabbed")); } }
          else if (grabbed === key && (event.key === "ArrowUp" || event.key === "ArrowDown")) { event.preventDefault(); move(key, value.order.indexOf(order[index + (event.key === "ArrowUp" ? -1 : 1)] ?? key)); }
          else if (grabbed === key && event.key === "Escape") { event.preventDefault(); event.stopPropagation(); if (before.current) onChange({ ...value, order: before.current }); setGrabbed(null); setMessage(word("cancelled")); }
        }}><GripVertical size={18} aria-hidden="true" /></button></> : null}
      </li>)}</ul>
      <span className={styles.srOnly} role="status" aria-live="polite">{message}</span>
    </section> : <section aria-label={word("height")}>{DENSITIES.map((density) => <label className={styles.choice} key={density}><input type="radio" name="records-preview-density" checked={value.density === density} onChange={() => onChange({ ...value, density })} /><span>{t(`business.transactions.density.${density}`)}</span></label>)}</section>}
    <div className={styles.settingsFooter}><button type="button" className={styles.clear} onClick={() => { before.current = null; setGrabbed(null); setDragging(null); setDropTarget(null); onRestore(); }}>{word("restore")}</button></div>
  </div>;
}
