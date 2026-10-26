"use client";

import { useEffect, useId, useReducer, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { FormField, useFieldChecks } from "@/components/ui/FormField";
import { resolveLanguage } from "@/lib/language-features";
import { formatDay, todayIso } from "../business-format";
import { isoOf, monthOf, shiftDay, weeks } from "./DatePicker";
import { createRangeDraft, dateInputFormat, parseRangeInput, presetRange, previewRange, reduceRangeDraft, shiftMonth, validDraftRange, type DateRange, type RangePreset } from "./range-picker-state";
import styles from "./range-picker.module.css";

const PRESETS: RangePreset[] = ["today", "yesterday", "last_7", "last_30", "last_quarter", "custom"];
const STEPS: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };

export function useRangePickerDraft(initial: DateRange, onConfirm: (range: DateRange) => void, maxDays = 366) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const [state, dispatch] = useReducer((draft: ReturnType<typeof createRangeDraft>, action: Parameters<typeof reduceRangeDraft>[1]) => reduceRangeDraft(draft, action, locale), initial, (range) => createRangeDraft(range, locale));
  const word = (key: string) => t(`business.date_range.${key}`);
  const invalid = t("business.date_range.invalid_date", { format: dateInputFormat(locale) });
  const checks = useFieldChecks({
    from: (text) => parseRangeInput(text.from, locale) ? null : invalid,
    to: (text) => {
      const end = parseRangeInput(text.to, locale);
      const start = parseRangeInput(text.from, locale);
      if (!end) return invalid;
      return start && (end < start || end > shiftDay(start, maxDays - 1)) ? t("business.date_range.invalid_range", { count: maxDays }) : null;
    },
  }, state.text);
  const range = validDraftRange(state, locale, maxDays);
  const confirm = () => { if (checks.submit() && range) onConfirm(range); };
  return { state, dispatch, locale, checks, range, confirm, word, invalid, maxDays };
}
export type RangePickerSession = ReturnType<typeof useRangePickerDraft>;

export function RangePickerConfirm({ session, phone = false }: { session: RangePickerSession; phone?: boolean }) {
  const { range, locale, word, confirm } = session;
  return <div className={phone ? styles.mobileConfirm : styles.footer}>
    <span className={styles.selection}>{range ? `${formatDay(range.from, locale)} · ${formatDay(range.to, locale)}` : word("complete_dates")}</span>
    <button type="button" className={styles.confirm} onClick={confirm}>{word("confirm")}</button>
  </div>;
}

export default function RangePicker({ session, phone = false, embedded = false }: { session: RangePickerSession; phone?: boolean; embedded?: boolean }) {
  const { state, dispatch, locale, checks, word } = session;
  const { t } = useTranslation();
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const grids = useRef<HTMLDivElement>(null);
  const focusCursor = useRef(false);
  const suppressClick = useRef(false);
  const [width, setWidth] = useState(embedded ? 320 : 900);
  const [view, setView] = useState(() => monthOf(state.cursor));
  const [mobileMonths, setMobileMonths] = useState(12);
  const columns = phone ? 1 : width >= 1160 ? 3 : width >= 830 ? 2 : 1;
  const monthCount = phone ? mobileMonths : columns;
  const today = todayIso();
  const preview = previewRange(state);
  const hovering = state.phase === "end" && state.hover !== null;
  useEffect(() => {
    const node = root.current;
    if (!node) return;
    const measure = () => { const next = node.getBoundingClientRect().width; if (next) setWidth(next); };
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(node);
    return () => observer?.disconnect();
  }, []);
  useEffect(() => {
    if (focusCursor.current) grids.current?.querySelector<HTMLButtonElement>(`[data-day="${state.cursor}"]`)?.focus({ preventScroll: false });
    focusCursor.current = false;
  }, [state.cursor, view]);
  const showCursor = (day: string, focus = true) => {
    const last = isoOf(view.year, view.month + monthCount, 0);
    if (day < isoOf(view.year, view.month, 1) || day > last) setView(monthOf(day));
    focusCursor.current = focus;
    dispatch({ type: "cursor", day });
  };
  const choosePreset = (preset: RangePreset) => {
    dispatch({ type: "preset", preset, today });
    checks.reset();
    if (preset !== "custom") {
      setView(monthOf(presetRange(preset, today).from));
      if (phone) window.requestAnimationFrame(() => grids.current?.scrollIntoView({ block: "start" }));
    }
  };
  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!(event.target as HTMLElement).closest("[data-day]")) return;
    if (STEPS[event.key] !== undefined) { event.preventDefault(); showCursor(shiftDay(state.cursor, STEPS[event.key])); }
    else if (event.key === "PageUp" || event.key === "PageDown") { event.preventDefault(); showCursor(shiftMonth(state.cursor, (event.key === "PageUp" ? -1 : 1) * (event.shiftKey ? 12 : 1))); }
    else if (event.key === "Enter" || event.key === " ") { event.preventDefault(); dispatch({ type: "pick", day: state.cursor }); checks.reset(); }
    else if (event.key === "Home" || event.key === "End") { event.preventDefault(); const month = monthOf(state.cursor); showCursor(isoOf(month.year, month.month + (event.key === "End" ? 1 : 0), event.key === "End" ? 0 : 1)); }
  };
  const hitDay = (event: PointerEvent<HTMLDivElement>) => {
    const hit = typeof document.elementFromPoint === "function" ? document.elementFromPoint(event.clientX, event.clientY) : event.target as Element;
    return hit?.closest<HTMLElement>("[data-day]")?.dataset.day;
  };
  const dragMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!state.drag) return;
    const day = hitDay(event);
    if (day) dispatch({ type: "drag-move", day });
  };
  const endDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (!state.drag) return;
    suppressClick.current = state.drag.moved;
    dispatch({ type: "drag-end" });
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    window.setTimeout(() => { suppressClick.current = false; }, 0);
  };
  const navigateMonth = (step: number) => { const day = shiftMonth(state.cursor, step); setView(monthOf(day)); dispatch({ type: "cursor", day }); };
  const monthViews = Array.from({ length: monthCount }, (_, index) => monthOf(isoOf(view.year, view.month + index, 1)));
  const presets = <div className={styles.presets} aria-label={word("presets")}>{PRESETS.filter((preset) => !phone || preset !== "today").map((preset) => <button key={preset} type="button" className={styles.preset} aria-pressed={state.preset === preset} onClick={() => choosePreset(preset)}>{word(`preset.${preset}`)}{state.preset === preset ? <Check size={15} aria-hidden="true" /> : null}</button>)}</div>;
  return <div ref={root} data-testid="range-picker" data-month-columns={columns} className={`${styles.picker} ${embedded ? styles.embedded : ""} ${phone ? styles.mobile : columns === 1 ? styles.narrow : ""}`}>
    <div className={styles.layout}>
      {embedded ? null : presets}
      <div className={styles.body}>
        <div className={styles.fields}>{(["from", "to"] as const).map((edge) => <FormField key={edge} id={`${id}-${edge}`} label={word(edge)} value={state.text[edge]} inputMode="text" autoComplete="off" placeholder={dateInputFormat(locale)} hint={dateInputFormat(locale)} error={checks.errorOf(edge)} success={checks.isValid(edge) ? word("valid_date") : undefined} reserveMessages={[]} onBlur={() => checks.blur(edge)} onChange={(event) => { dispatch({ type: "type", edge, text: event.target.value }); const day = parseRangeInput(event.target.value, locale); if (day && (day < isoOf(view.year, view.month, 1) || day > isoOf(view.year, view.month + monthCount, 0))) setView(monthOf(day)); }} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); session.confirm(); } }} />)}</div>
        <div className={styles.navigation}>
          <button type="button" className={styles.icon} aria-label={t("business.date_picker.previous_month")} onClick={() => navigateMonth(-1)}><ChevronLeft size={18} aria-hidden="true" /></button>
          <button type="button" className={styles.today} onClick={() => choosePreset("today")}>{word("preset.today")}</button>
          <button type="button" className={styles.icon} aria-label={t("business.date_picker.next_month")} onClick={() => navigateMonth(1)}><ChevronRight size={18} aria-hidden="true" /></button>
        </div>
        <div ref={grids} className={styles.months} style={phone ? undefined : { gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }} onKeyDown={onKey} onPointerMove={dragMove} onPointerUp={endDrag} onPointerCancel={() => dispatch({ type: "drag-cancel" })} onPointerLeave={() => { if (!state.drag) dispatch({ type: "hover", day: null }); }}>
          {monthViews.map((month) => {
            const title = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(month.year, month.month, 1)));
            return <section key={`${month.year}-${month.month}`}><h3 className={styles.monthTitle}>{title.charAt(0).toLocaleUpperCase(locale) + title.slice(1)}</h3><table role="grid" aria-label={title} className={styles.month}><thead><tr>{t("business.date_picker.weekdays").split(" ").map((day) => <th key={day} scope="col">{day}</th>)}</tr></thead><tbody>{weeks(month).map((week, index) => <tr key={index}>{week.map((day, column) => {
              if (!day) return <td key={`empty-${column}`} />;
              const start = day === preview.from; const end = day === preview.to; const inside = day >= preview.from && day <= preview.to;
              const selected = day >= state.range.from && day <= state.range.to;
              const edge = day === state.range.from || day === state.range.to;
              return <td key={day} role="gridcell" aria-selected={selected} data-range-preview={hovering && inside ? "true" : undefined} className={`${inside ? hovering ? styles.preview : styles.inside : ""} ${start ? styles.start : ""} ${end ? styles.end : ""} ${start && end ? styles.single : ""} ${edge ? styles.edge : ""} ${hovering && (start || end) ? styles.previewEdge : ""} ${day === today ? styles.todayDay : ""}`}><button type="button" data-day={day} className={styles.day} tabIndex={day === state.cursor ? 0 : -1} aria-label={formatDay(day, locale)} aria-current={day === today ? "date" : undefined} onFocus={() => dispatch({ type: "cursor", day })} onPointerEnter={() => { if (state.drag) dispatch({ type: "drag-move", day }); else dispatch({ type: "hover", day }); }} onPointerDown={(event) => { if (event.button === 0 && edge && state.phase === "start") { dispatch({ type: "drag-start", edge: day === state.range.from ? "from" : "to" }); grids.current?.setPointerCapture?.(event.pointerId); } }} onClick={() => { if (suppressClick.current) { suppressClick.current = false; return; } dispatch({ type: "pick", day }); checks.reset(); }}>{Number(day.slice(8))}</button></td>;
            })}</tr>)}</tbody></table></section>;
          })}
        </div>
        {phone ? <button type="button" className={styles.load} onClick={() => setMobileMonths((count) => count + 6)}>{word("more_months")}</button> : null}
        <p className="sr-only" aria-live="polite">{state.phase === "end" ? word("pick_end") : word("pick_start")}</p>
      </div>
    </div>
  </div>;
}
