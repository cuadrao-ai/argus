"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
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

/** A typed dd/mm/aaaa (or ddmmaaaa, from a phone number pad) day as ISO, or null when it is not a real calendar day. */
export function parseDayText(text: string): string | null {
  const parts = /^(\d{2})\/?(\d{2})\/?(\d{4})$/.exec(text.trim());
  if (!parts || Number(parts[3]) < 1900) return null;
  const iso = `${parts[3]}-${parts[2]}-${parts[1]}`;
  const parsed = new Date(`${iso}T12:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === iso ? iso : null;
}

export function monthOf(iso: string): Month {
  const [year, month] = iso.split("-").map(Number);
  return { year, month: month - 1 };
}

export function isoOf(year: number, month: number, day: number): string {
  return new Date(Date.UTC(year, month, day)).toISOString().slice(0, 10);
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

const KEY_STEP: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
const focusRing = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49]";
const iconButton = `inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-[#172b26] disabled:opacity-40 dark:text-white ${focusRing}`;

/**
 * The one single-date field: shows the day as "14 oct 2026", takes a typed
 * dd/mm/aaaa, and opens one Monday-first month with Hoy and Ayer. On a
 * phone the month opens as a bottom sheet. Values are ISO days.
 */
export function DatePicker({ id, label, value, onChange, disabled }: {
  id?: string;
  /** The field's name, which also names the phone sheet. */
  label: string;
  value: string;
  onChange: (iso: string | null, invalid: boolean) => void;
  disabled?: boolean;
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
  }, [open, active]);


  const show = () => {
    setActive(typed ?? todayIso());
    focusDay.current = true;
    setOpen(true);
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

  const view = monthOf(active);
  const today = todayIso();
  const yesterday = shiftDay(today, -1);
  const monthTitle = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(view.year, view.month, 1)));
  const weekdays = t("business.date_picker.weekdays", "lu ma mi ju vi sá do").split(" ");

  const month = (
    <div data-testid="date-picker-month" className="business-foundation">
      <div className="flex gap-2">
        <button type="button" className={`${quietButtonClass} px-3`} onClick={() => choose(today)}>{t("business.date_picker.today", "Today")}</button>
        <button type="button" className={`${quietButtonClass} px-3`} onClick={() => choose(yesterday)}>{t("business.date_picker.yesterday", "Yesterday")}</button>
      </div>
      <div className="mt-2 flex items-center justify-between gap-2">
        <button type="button" className={iconButton} aria-label={t("business.date_picker.previous_month", "Previous month")} onClick={() => turn(-1)}>
          <ChevronLeft className="h-5 w-5" aria-hidden="true" />
        </button>
        <h2 id={headingId} aria-live="polite" className="font-display text-[18px] font-medium leading-6 text-[#172b26] dark:text-white">{monthTitle}</h2>
        <button type="button" className={iconButton} aria-label={t("business.date_picker.next_month", "Next month")} onClick={() => turn(1)}>
          <ChevronRight className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>
      <table role="grid" aria-labelledby={headingId} className="mx-auto mt-2 border-collapse" onKeyDown={onGridKey}>
        <thead>
          <tr>{weekdays.map((day) => <th key={day} scope="col" className="h-8 w-11 text-[12px] font-medium text-[#56635e] dark:text-white/70">{day}</th>)}</tr>
        </thead>
        <tbody>
          {weeks(view).map((week, row) => (
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
          aria-invalid={Boolean(text) && !typed}
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
