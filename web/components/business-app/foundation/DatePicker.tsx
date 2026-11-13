"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { CalendarDays, ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import BottomSheet from "@/components/ui/BottomSheet";
import { formatDay, todayIso } from "../business-format";
import { quietButtonClass } from "../business-ui";
import { resolveLanguage } from "@/lib/language-features";

export type Month = { year: number; month: number };

export function dayText(iso: string): string {
  return iso ? iso.split("-").reverse().join("/") : "";
}

/**
 * A typed day as ISO, or null when it is not a real calendar day. Takes d/m/aa
 * and d/m/aaaa, or ddmmaa and ddmmaaaa from a phone number pad. A 2-digit year
 * is 20aa. Digits without slashes in any other count could mean two days.
 */
export function parseDayText(text: string): string | null {
  const parts = /^(\d{1,2})\/(\d{1,2})\/(\d{2}|\d{4})$/.exec(text.trim()) ?? /^(\d{2})(\d{2})(\d{2}|\d{4})$/.exec(text.trim());
  if (!parts) return null;
  const [day, month, year] = [Number(parts[1]), Number(parts[2]), parts[3].length === 2 ? 2000 + Number(parts[3]) : Number(parts[3])];
  if (year < 1900) return null;
  const iso = isoOf(year, month - 1, day);
  return iso === `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}` ? iso : null;
}

export function monthOf(iso: string): Month {
  const [year, month] = iso.split("-").map(Number);
  return { year, month: month - 1 };
}

export function isoOf(year: number, month: number, day: number): string {
  return new Date(Date.UTC(year, month, day)).toISOString().slice(0, 10);
}

/** The same day of the month in another month, or that month's last day when it is shorter: 29 feb 2024 in 2026 is 28 feb. */
export function dayIn(iso: string, year: number, month: number): string {
  return isoOf(year, month, Math.min(Number(iso.slice(8)), new Date(Date.UTC(year, month + 1, 0)).getUTCDate()));
}

/** The day moved into the year the document was uploaded, or null when it is already there. */
export function inUploadYear(day: string, uploadYear: number): string | null {
  const { year, month } = monthOf(day);
  return year === uploadYear ? null : dayIn(day, uploadYear, month);
}

export function shiftDay(iso: string, days: number): string {
  const [year, month, day] = iso.split("-").map(Number);
  return isoOf(year, month - 1, day + days);
}

/** The month's days in Monday-first weeks; null fills the cells outside the month. */
export function weeks({ year, month }: Month): (string | null)[][] {
  const lead = (new Date(Date.UTC(year, month, 1)).getUTCDay() + 6) % 7;
  const length = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const cells = [...Array(lead).fill(null), ...Array.from({ length }, (_, index) => isoOf(year, month, index + 1))];
  while (cells.length % 7) cells.push(null);
  return Array.from({ length: cells.length / 7 }, (_, row) => cells.slice(row * 7, row * 7 + 7));
}

/**
 * What the field holds decides the month's shortcuts. A past day offers Hoy and
 * Ayer, a due day offers days ahead, and a document's own date offers none: it
 * offers the upload year instead, from the time the server received the document.
 */
export type DateFieldContext = { kind: "past" } | { kind: "due" } | { kind: "document"; uploadedAt: string | null };
type CalendarView = "days" | "months" | "years";
const RECENT_YEARS = 12;

const KEY_STEP: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
const focusRing = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49]";
const iconButton = `inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-[#172b26] disabled:opacity-40 dark:text-white ${focusRing}`;
const headerButton = `inline-flex min-h-11 items-center gap-1 rounded-item px-2 hover:bg-black/[0.04] dark:hover:bg-white/[0.06] ${focusRing}`;
const choiceButton = (chosen: boolean) => `min-h-11 rounded-item px-2 text-[15px] tabular-nums ${focusRing} ${chosen ? "bg-[#2f5a49] font-medium text-[#FFFEFA]" : "text-[#172b26] hover:bg-black/[0.04] dark:text-white dark:hover:bg-white/[0.06]"}`;

/**
 * The one single-date field: shows the day as "14 oct 2026", takes a typed
 * d/m/aa, and opens one Monday-first month. Its header jumps to a month and a
 * year. On a phone the month opens as a bottom sheet. Values are ISO days.
 */
export function DatePicker({ id, label, value, onChange, disabled, invalid, describedBy, context = { kind: "past" } }: {
  id?: string;
  /** The field's name, which also names the phone sheet. */
  label: string;
  value: string;
  onChange: (iso: string | null, invalid: boolean) => void;
  disabled?: boolean;
  invalid?: boolean;
  describedBy?: string;
  context?: DateFieldContext;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const ownId = useId();
  const inputId = id ?? `${ownId}-input`;
  const headingId = `${ownId}-month`;
  const popoverId = `${ownId}-popover`;
  const [text, setText] = useState(() => dayText(value));
  const [seen, setSeen] = useState(value);
  const [focused, setFocused] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(() => value || todayIso());
  const [view, setView] = useState<CalendarView>("days");
  const { isBelowTablet } = useResponsiveLayout();
  const root = useRef<HTMLDivElement>(null);
  const activeDay = useRef<HTMLButtonElement>(null);
  const field = useRef<HTMLInputElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const focusDay = useRef(false);

  // The parent's value changed by something other than this field: show it.
  if (value !== seen) {
    setSeen(value);
    setText(dayText(value));
  }
  const emit = (next: string, iso: string | null, invalid: boolean) => {
    setText(next);
    setSeen(iso ?? "");
    onChange(iso, invalid);
  };

  const typed = parseDayText(text);
  const shown = focused || (text && !typed) ? text : formatDay(typed, locale);

  // Focus swaps the shown day for its dd/mm/aaaa form, so the new text is selected for typing over.
  useEffect(() => {
    if (focused) field.current?.select();
  }, [focused]);

  useEffect(() => {
    if (!open || !focusDay.current) return;
    focusDay.current = false;
    activeDay.current?.focus();
  }, [open, active, view]);


  const show = () => {
    setActive(typed ?? todayIso());
    setView("days");
    focusDay.current = true;
    setOpen(true);
  };
  const look = (next: CalendarView, day = active) => {
    setActive(day);
    setView(next);
    focusDay.current = true;
  };
  const close = () => {
    setOpen(false);
    trigger.current?.focus();
  };
  const choose = (iso: string) => {
    emit(dayText(iso), iso, false);
    close();
  };
  const turn = (step: number) => setActive((current) => {
    const { year, month } = monthOf(current);
    return isoOf(year, month + step, 1);
  });
  useOverlayLayer({
    isOpen: open && !isBelowTablet,
    overlayId: popoverId,
    containerRef: root,
    onEscape: close,
    onOutsidePointerDown: () => setOpen(false),
  });
  const onGridKey = (event: KeyboardEvent) => {
    const step = KEY_STEP[event.key];
    if (step === undefined) return;
    event.preventDefault();
    focusDay.current = true;
    setActive((current) => shiftDay(current, step));
  };

  const shownMonth = monthOf(active);
  const today = todayIso();
  const yesterday = shiftDay(today, -1);
  const [year, monthNumber, day] = today.split("-").map(Number);
  const nextMonth = isoOf(year, monthNumber, Math.min(day, new Date(Date.UTC(year, monthNumber + 1, 0)).getUTCDate()));
  const quickDates = {
    past: [{ key: "today", date: today }, { key: "yesterday", date: yesterday }],
    due: [{ key: "today", date: today }, { key: "in_7_days", date: shiftDay(today, 7) }, { key: "in_15_days", date: shiftDay(today, 15) }, { key: "in_one_month", date: nextMonth }],
    document: [],
  }[context.kind];
  const uploadYear = context.kind === "document" && context.uploadedAt ? new Date(context.uploadedAt).getFullYear() : null;
  const uploadFix = typed && uploadYear && !Number.isNaN(uploadYear) ? inUploadYear(typed, uploadYear) : null;
  const monthName = (month: number, style: "long" | "short") => new Intl.DateTimeFormat(locale, style === "long" ? { month: "long", year: "numeric", timeZone: "UTC" } : { month: "short", timeZone: "UTC" }).format(new Date(Date.UTC(shownMonth.year, month, 1)));
  const monthTitle = monthName(shownMonth.month, "long");
  const newestYear = Math.max(year, uploadYear ?? year);
  const years = Array.from({ length: RECENT_YEARS }, (_, index) => newestYear - index);
  const weekdays = t("business.date_picker.weekdays", "lu ma mi ju vi sá do").split(" ");

  const heading = (text: string, next?: CalendarView) => (
    <h2 id={headingId} aria-live="polite" className="font-display text-[18px] font-medium leading-6 text-[#172b26] dark:text-white">
      {next ? <button type="button" className={headerButton} onClick={() => look(next)}>{text}<ChevronDown className="h-4 w-4" aria-hidden="true" /></button> : text}
    </h2>
  );
  const uploadNote = uploadFix ? (
    <div data-testid="date-picker-upload-year" role="note" className="mb-2 flex flex-wrap items-center gap-x-2 rounded-item bg-[#f2e8c9] pl-3 text-[14px] text-[#735c14] dark:bg-[#f6e7c1]/15 dark:text-[#f6e7c1]">
      <span>{t("business.date_picker.uploaded_in", { year: String(uploadYear) })}</span>
      <button type="button" className={`min-h-11 rounded-item px-2 font-medium underline underline-offset-2 ${focusRing}`} onClick={() => choose(uploadFix)}>{t("business.date_picker.use_date", { date: formatDay(uploadFix, locale) })}</button>
    </div>
  ) : null;
  const months = (
    <>
      <div className="flex items-center justify-between gap-2">
        <button type="button" className={iconButton} aria-label={String(shownMonth.year - 1)} onClick={() => look("months", dayIn(active, shownMonth.year - 1, shownMonth.month))}>
          <ChevronLeft className="h-5 w-5" aria-hidden="true" />
        </button>
        {heading(String(shownMonth.year), "years")}
        <button type="button" className={iconButton} aria-label={String(shownMonth.year + 1)} onClick={() => look("months", dayIn(active, shownMonth.year + 1, shownMonth.month))}>
          <ChevronRight className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>
      <div data-testid="date-picker-months" role="group" aria-labelledby={headingId} className="mt-2 grid w-[308px] grid-cols-3 gap-1">
        {Array.from({ length: 12 }, (_, month) => (
          <button key={month} type="button" ref={month === shownMonth.month ? activeDay : undefined} aria-label={monthName(month, "long")} className={choiceButton(typed?.slice(0, 7) === isoOf(shownMonth.year, month, 1).slice(0, 7))} onClick={() => look("days", dayIn(active, shownMonth.year, month))}>
            {monthName(month, "short")}
          </button>
        ))}
      </div>
    </>
  );
  const yearList = (
    <>
      <div className="flex min-h-11 items-center justify-center">{heading(String(shownMonth.year))}</div>
      <div data-testid="date-picker-years" role="group" aria-labelledby={headingId} className="mt-2 grid w-[308px] grid-cols-3 gap-1">
        {years.map((choice) => (
          <button key={choice} type="button" data-year={choice} ref={choice === shownMonth.year ? activeDay : undefined} className={`${choiceButton(choice === Number(typed?.slice(0, 4)))} flex flex-col items-center justify-center`} onClick={() => look("days", dayIn(active, choice, shownMonth.month))}>
            {choice}
            {choice === uploadYear ? <span data-upload-year className="text-[11px] leading-3 text-[#735c14] dark:text-[#f6e7c1]">{t("business.date_picker.uploaded_in", { year: String(uploadYear) })}</span> : null}
          </button>
        ))}
      </div>
    </>
  );
  const days = (
    <>
      {quickDates.length ? (
        <div className="mb-2 flex flex-wrap gap-1">
          {quickDates.map(preset => <button key={preset.key} type="button" className={`${quietButtonClass} px-2 text-sm`} onClick={() => choose(preset.date)}>{t(`business.date_picker.${preset.key}`)}</button>)}
        </div>
      ) : null}
      <div className="flex items-center justify-between gap-2">
        <button type="button" className={iconButton} aria-label={t("business.date_picker.previous_month", "Previous month")} onClick={() => turn(-1)}>
          <ChevronLeft className="h-5 w-5" aria-hidden="true" />
        </button>
        {heading(monthTitle, "months")}
        <button type="button" className={iconButton} aria-label={t("business.date_picker.next_month", "Next month")} onClick={() => turn(1)}>
          <ChevronRight className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>
      <table role="grid" aria-labelledby={headingId} className="mx-auto mt-2 border-collapse" onKeyDown={onGridKey}>
        <thead>
          <tr>{weekdays.map((day) => <th key={day} scope="col" className="h-8 w-11 text-[12px] font-medium text-[#56635e] dark:text-white/70">{day}</th>)}</tr>
        </thead>
        <tbody>
          {weeks(shownMonth).map((week, row) => (
            <tr key={row}>
              {week.map((day, column) => (
                <td key={day ?? `empty-${column}`} role={day ? "gridcell" : undefined} aria-selected={day ? day === typed : undefined} className="p-0">
                  {day ? (
                    <button
                      type="button"
                      ref={day === active ? activeDay : undefined}
                      tabIndex={day === active ? 0 : -1}
                      aria-label={formatDay(day, locale)}
                      aria-current={day === today ? "date" : undefined}
                      data-day={day}
                      onClick={() => choose(day)}
                      className={`h-11 w-11 rounded-full ${focusRing} text-[15px] tabular-nums ${day === typed ? "bg-[#2f5a49] font-medium text-[#FFFEFA]" : day === today ? "border border-[#2f5a49] font-medium text-[#172b26] dark:text-white" : "text-[#172b26] dark:text-white"}`}
                    >
                      {Number(day.slice(8))}
                    </button>
                  ) : null}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
  const month = (
    <div data-testid="date-picker-month" className="business-foundation">
      {uploadNote}
      {{ days, months, years: yearList }[view]}
    </div>
  );

  return (
    <div
      ref={root}
      className="relative"
      onBlur={(event) => { if (open && !isBelowTablet && event.relatedTarget && !root.current?.contains(event.relatedTarget as Node)) setOpen(false); }}
    >
      <div className="flex min-h-11 items-center rounded-item border border-[#7d8a84] bg-[#FFFEFA] dark:bg-[#141517]">
        <input
          ref={field}
          id={inputId}
          type="text"
          inputMode="numeric"
          autoComplete="off"
          placeholder={t("business.date_picker.placeholder", "dd/mm/aaaa")}
          className={`min-h-11 min-w-0 flex-1 rounded-item bg-transparent pl-3 text-[16px] text-[#172b26] placeholder:text-[#687A72] disabled:opacity-50 dark:text-white ${focusRing}`}
          value={shown}
          disabled={disabled}
          aria-invalid={Boolean(invalid || (text && !typed))}
          aria-describedby={describedBy}
          onFocus={() => setFocused(true)}
          onBlur={() => { setFocused(false); if (typed) setText(dayText(typed)); }}
          onChange={(event) => {
            const next = event.target.value;
            const iso = parseDayText(next);
            emit(next, iso, Boolean(next) && !iso);
          }}
        />
        <button
          ref={trigger}
          type="button"
          disabled={disabled}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls={open && !isBelowTablet ? popoverId : undefined}
          aria-label={t("business.date_picker.open", "Open calendar")}
          className={iconButton}
          onClick={() => (open ? close() : show())}
        >
          <CalendarDays className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>
      {open && !isBelowTablet ? (
        <div id={popoverId} role="dialog" aria-labelledby={headingId} data-testid="date-picker-dialog" className="absolute left-0 top-full z-[70] mt-2 w-max rounded-surface border border-[#DCE0DA] bg-[#FFFEFA] p-4 shadow-lg dark:border-white/10 dark:bg-[#1f2225]">
          {month}
        </div>
      ) : null}
      {isBelowTablet ? (
        <BottomSheet isOpen={open} onClose={close} title={label} titleHidden closeLabel={t("common.close", "Close")} snaps="fit" initialFocusRef={activeDay}>
          {month}
        </BottomSheet>
      ) : null}
    </div>
  );
}
