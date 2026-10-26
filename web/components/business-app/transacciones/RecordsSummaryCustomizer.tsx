"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { ArrowDown, ArrowUp, GripVertical, SlidersHorizontal } from "lucide-react";
import BottomSheet from "@/components/ui/BottomSheet";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import RecordsPreviewPopover from "./RecordsPreviewPopover";
import { DEFAULT_SUMMARY_METRICS, SUMMARY_METRICS, type SummaryMetric } from "./records-results-preview";
import { useTransaccionesWords } from "./transacciones-words";
import controls from "./records-filter-preview.module.css";
import styles from "./records-results-preview.module.css";

export default function RecordsSummaryCustomizer({ selected, onChange }: { selected: readonly SummaryMetric[]; onChange: (value: SummaryMetric[]) => void }) {
  const { t } = useTransaccionesWords();
  const { isBelowDesktop: phone } = useResponsiveLayout();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);
  const cancelMove = useRef<(() => boolean) | null>(null);
  const registerCancel = useCallback((handler: (() => boolean) | null) => { cancelMove.current = handler; }, []);
  useEffect(() => { if (wasOpen.current && !open) trigger.current?.focus(); wasOpen.current = open; }, [open]);
  const title = t("business.transactions.layout.results.customize");
  const editor = (close: () => void) => <MetricEditor initial={selected} apply={onChange} close={close} phone={phone} registerCancel={registerCancel} />;
  if (phone) return <><button ref={trigger} type="button" className={controls.trigger} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}><SlidersHorizontal size={16} aria-hidden="true" />{title}</button>{open ? editor(() => setOpen(false)) : null}</>;
  return <RecordsPreviewPopover label={title} icon={<SlidersHorizontal size={16} aria-hidden="true" />} width={380} preferredHeight={390} beforeEscape={() => cancelMove.current?.() ?? false}>{editor}</RecordsPreviewPopover>;
}

function MetricEditor({ initial, apply, close, phone, registerCancel }: { initial: readonly SummaryMetric[]; apply: (value: SummaryMetric[]) => void; close: () => void; phone: boolean; registerCancel: (handler: (() => boolean) | null) => void }) {
  const { t } = useTransaccionesWords();
  const word = (key: string) => t(`business.transactions.layout.results.${key}`);
  const label = (key: SummaryMetric) => word(`metrics.${key}`);
  const [draft, setDraft] = useState<SummaryMetric[]>(() => [...initial]);
  const [grabbed, setGrabbed] = useState<SummaryMetric | null>(null);
  const before = useRef<SummaryMetric[] | null>(null);
  const [dragging, setDragging] = useState<SummaryMetric | null>(null);
  const [target, setTarget] = useState<SummaryMetric | null>(null);
  const [message, setMessage] = useState("");
  const hintId = useId();
  useEffect(() => {
    registerCancel(() => {
      if (!grabbed) return false;
      if (before.current) setDraft(before.current);
      setGrabbed(null); setMessage(t("business.transactions.layout.results.order_cancelled")); return true;
    });
    return () => registerCancel(null);
  }, [registerCancel, grabbed, t]);
  const move = (key: SummaryMetric, position: number) => {
    const next = draft.filter((metric) => metric !== key);
    const index = Math.max(0, Math.min(next.length, position));
    next.splice(index, 0, key); setDraft(next);
    setMessage(t("business.transactions.layout.results.position", { name: label(key), position: index + 1, count: next.length }));
  };
  const toggle = (key: SummaryMetric) => { setGrabbed(null); before.current = null; setDraft(draft.includes(key) ? draft.filter((metric) => metric !== key) : [...draft, key]); };
  const ordered = [...draft, ...SUMMARY_METRICS.filter((key) => !draft.includes(key))];
  const body = <div className={styles.customizer}>
    <p id={hintId} className={controls.hint}>{word(phone ? "choose_phone" : "choose_desktop")}</p>
    <ul className={styles.metricChoices}>{ordered.map((key) => {
      const index = draft.indexOf(key);
      return <li key={key} data-metric-option={key} className={`${styles.metricChoice} ${target === key ? (dragging && draft.indexOf(dragging) < index ? controls.dropAfter : controls.dropBefore) : ""}`} onDragOver={(event) => { if (dragging && index >= 0) { event.preventDefault(); setTarget(dragging === key ? null : key); } }} onDrop={(event) => { event.preventDefault(); if (dragging && index >= 0) move(dragging, index); setDragging(null); setTarget(null); }}>
        <label className={controls.choice}><input type="checkbox" checked={index >= 0} onChange={() => toggle(key)} /><span>{label(key)}</span></label>
        {index >= 0 ? phone ? <div className={styles.moveButtons}><button type="button" className={controls.iconButton} disabled={index === 0} aria-label={t("business.transactions.layout.results.move_up", { name: label(key) })} onClick={() => move(key, index - 1)}><ArrowUp size={17} aria-hidden="true" /></button><button type="button" className={controls.iconButton} disabled={index === draft.length - 1} aria-label={t("business.transactions.layout.results.move_down", { name: label(key) })} onClick={() => move(key, index + 1)}><ArrowDown size={17} aria-hidden="true" /></button></div> : <button type="button" className={controls.grip} draggable aria-label={t("business.transactions.layout.results.move", { name: label(key) })} aria-describedby={hintId} aria-pressed={grabbed === key} onDragStart={(event) => { setDragging(key); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", key); }} onDragEnd={() => { setDragging(null); setTarget(null); }} onKeyDown={(event) => {
          if (event.key === " ") { event.preventDefault(); if (grabbed === key) { setGrabbed(null); before.current = null; setMessage(word("order_placed")); } else { before.current = [...draft]; setGrabbed(key); setMessage(word("order_grabbed")); } }
          else if (grabbed === key && (event.key === "ArrowUp" || event.key === "ArrowDown")) { event.preventDefault(); move(key, index + (event.key === "ArrowUp" ? -1 : 1)); }
        }}><GripVertical size={18} aria-hidden="true" /></button> : null}
      </li>;
    })}</ul>
    <span role="status" aria-live="polite" className={controls.srOnly}>{message}</span>
  </div>;
  const footer = <div className={`${controls.footer} ${phone ? controls.phoneFooter : ""}`}><button type="button" className={controls.clear} onClick={() => { setDraft([...DEFAULT_SUMMARY_METRICS]); setGrabbed(null); before.current = null; }}>{word("restore")}</button><button type="button" className={controls.apply} onClick={() => { apply(draft); close(); }}>{t("business.transactions.layout.filters.apply")}</button></div>;
  return phone ? <BottomSheet isOpen onClose={close} title={word("customize")} closeLabel={t("common.close")} snaps="fit" footer={footer}>{body}</BottomSheet> : <>{body}{footer}</>;
}
