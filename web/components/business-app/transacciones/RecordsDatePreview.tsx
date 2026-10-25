"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { CalendarDays, Check, ChevronLeft, ChevronRight } from "lucide-react";
import { customPeriod, formatDay, periodRange, PERIOD_PRESETS, todayIso, type Period, type PeriodKey } from "../business-format";
import { usePeriodLabel } from "../BusinessPeriodControl";
import { isoOf, monthOf, shiftDay, weeks } from "../foundation/DatePicker";
import { pickDay, type DayRange } from "../foundation/RangeCalendar";
import RecordsPreviewPopover from "./RecordsPreviewPopover";
import { useTransaccionesWords } from "./transacciones-words";
import styles from "./records-filter-preview.module.css";

const DAY_STEP: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };

function ExpandedCalendar({ initial, apply, close }: { initial: Period; apply: (next: Period) => void; close: () => void }) {
  const { t, locale } = useTransaccionesWords();
  const name = usePeriodLabel();
  const [range, setRange] = useState<DayRange>({ from: initial.from, to: initial.to ?? todayIso() });
  const [preset, setPreset] = useState<PeriodKey>(initial.key);
  const [phase, setPhase] = useState<"start" | "end">("start");
  const initialDay = initial.key === "all" ? todayIso() : initial.from;
  const [active, setActive] = useState(initialDay);
  const [view, setView] = useState(() => monthOf(initialDay));
  const grid = useRef<HTMLDivElement>(null);
  const moved = useRef(false);
  const second = monthOf(isoOf(view.year, view.month + 1, 1));
  const latest = phase === "end" ? shiftDay(range.from, 365) : null;
  const custom = customPeriod(range.from, range.to);
  const next = preset === "custom" ? custom && range.to <= shiftDay(range.from, 365) ? custom : null : periodRange(preset);
  useEffect(() => {
    if (moved.current) grid.current?.querySelector<HTMLButtonElement>(`[data-day="${active}"]`)?.focus();
    moved.current = false;
  }, [active]);
  const movePair = (direction: number) => {
    const day = isoOf(view.year, view.month + direction * 2, 1);
    setView(monthOf(day));
    setActive(day);
  };
  const choosePreset = (key: PeriodKey) => {
    setPreset(key);
    if (key === "custom") return;
    const period = periodRange(key);
    const chosen = { from: period.from, to: period.to ?? todayIso() };
    setRange(chosen);
    const day = key === "all" ? todayIso() : chosen.from;
    setView(monthOf(day));
    setActive(day);
    setPhase("start");
  };
  const selectDay = (day: string) => {
    const picked = pickDay(range, phase, day);
    setRange(picked.range);
    setPhase(picked.phase);
    setPreset("custom");
    setActive(day);
  };
  const onKey = (event: KeyboardEvent) => {
    const step = DAY_STEP[event.key];
    if (step === undefined) return;
    event.preventDefault();
    const day = shiftDay(active, step);
    const end = isoOf(second.year, second.month + 1, 0);
    if (day < isoOf(view.year, view.month, 1) || day > end) setView(monthOf(day));
    moved.current = true;
    setActive(day);
  };
  const updateDate = (key: keyof DayRange, day: string) => {
    setRange({ ...range, [key]: day });
    setPreset("custom");
    if (/^\d{4}-\d{2}-\d{2}$/.test(day)) { setView(monthOf(day)); setActive(day); }
    setPhase(key === "from" ? "end" : "start");
  };
  return <>
    <div className={styles.calendarPanel}>
      <div className={styles.rail}>{[...PERIOD_PRESETS, "custom" as const].map((key) => <button key={key} type="button" className={styles.group} aria-pressed={preset === key} onClick={() => choosePreset(key)}><span>{key === "custom" ? t("business.period.custom") : name({ ...initial, key })}</span>{preset === key ? <Check size={16} aria-hidden="true" /> : null}</button>)}</div>
      <div className={styles.calendarBody}>
        <div className={styles.calendarInputs}>{(["from", "to"] as const).map((key) => <label key={key} className={styles.field}><span>{t(`business.transactions.layout.filters.date.${key}`)}</span><input type="date" className={styles.input} value={range[key]} onChange={(event) => updateDate(key, event.target.value)} /></label>)}</div>
        <div className={styles.monthNavigation}><button type="button" className={styles.iconButton} aria-label={t("business.date_picker.previous_month")} onClick={() => movePair(-1)}><ChevronLeft size={18} aria-hidden="true" /></button><button type="button" className={styles.iconButton} aria-label={t("business.date_picker.next_month")} onClick={() => movePair(1)}><ChevronRight size={18} aria-hidden="true" /></button></div>
        <div ref={grid} className={styles.months} onKeyDown={onKey}>
          {[view, second].map((month) => {
            const title = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(month.year, month.month, 1)));
            return <div key={`${month.year}-${month.month}`}><h3 className={styles.monthTitle}>{title}</h3><table role="grid" aria-label={title} className={styles.month}><thead><tr>{t("business.date_picker.weekdays").split(" ").map((day) => <th key={day} scope="col">{day}</th>)}</tr></thead><tbody>{weeks(month).map((week, index) => <tr key={index}>{week.map((day, column) => {
              if (!day) return <td key={`empty-${column}`} />;
              const edge = day === range.from || day === range.to;
              const inside = day > range.from && day < range.to;
              return <td key={day} role="gridcell" aria-selected={edge || inside} className={`${inside ? styles.inside : ""} ${edge ? styles.edge : ""}`}><button type="button" className={styles.day} data-day={day} tabIndex={day === active ? 0 : -1} disabled={latest !== null && day > latest} aria-label={formatDay(day, locale)} onClick={() => selectDay(day)}>{Number(day.slice(8))}</button></td>;
            })}</tr>)}</tbody></table></div>;
          })}
        </div>
        <p className="sr-only" aria-live="polite">{phase === "end" ? t("business.export.pick_end") : ""}</p>
        {!next ? <p role="alert" className={styles.error}>{t("business.transactions.layout.filters.date.invalid")}</p> : null}
      </div>
    </div>
    <div className={styles.footer}><span /><button type="button" className={styles.apply} disabled={!next} onClick={() => { if (next) { apply(next); close(); } }}>{t("business.transactions.layout.filters.apply")}</button></div>
  </>;
}

export default function RecordsDatePreview({ period, value, onChange }: { period: Period; value?: Period; onChange?: (next: Period) => void }) {
  const [localPeriod, setLocalPeriod] = useState(period);
  const selected = value ?? localPeriod;
  const setSelected = (next: Period) => { if (onChange) onChange(next); else setLocalPeriod(next); };
  const name = usePeriodLabel();
  return <RecordsPreviewPopover label={name(selected)} icon={<CalendarDays size={17} aria-hidden="true" />} width={850}>{(close) => <ExpandedCalendar initial={selected} apply={setSelected} close={close} />}</RecordsPreviewPopover>;
}
