"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatDay, todayIso } from "../business-format";
import { isoOf, monthOf, shiftDay, weeks } from "./DatePicker";

export type DayRange = { from: string; to: string };
type Phase = "start" | "end";

const KEY_STEP: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
const focusRing = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49]";
const iconButton = `inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-[#172b26] dark:text-white ${focusRing}`;

/** The second tap ends the range; a day before the start starts it over. */
export function pickDay(range: DayRange, phase: Phase, day: string): { range: DayRange; phase: Phase } {
  if (phase === "start" || day < range.from) return { range: { from: day, to: day }, phase: "end" };
  return { range: { from: range.from, to: day }, phase: "start" };
}

/**
 * One month, two taps: the first picks where the range starts, the second
 * where it ends. It sits in the page, not in a popover, so it never spills
 * out of the sheet that holds it. `maxDays` greys out ends past the limit.
 */
export function RangeCalendar({ value, onChange, maxDays, label }: { value: DayRange; onChange: (range: DayRange) => void; maxDays: number; label: string }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "es-419";
  const [phase, setPhase] = useState<Phase>("start");
  // Opens on the range's last month, or on this month when the range runs into the future.
  const [active, setActive] = useState(() => (value.to > todayIso() && value.from <= todayIso() ? todayIso() : value.to));
  const [view, setView] = useState(() => monthOf(active));
  const activeDay = useRef<HTMLButtonElement>(null);
  const moved = useRef(false);
  useEffect(() => {
    if (moved.current) activeDay.current?.focus();
    moved.current = false;
  }, [active]);

  const latest = phase === "end" ? shiftDay(value.from, maxDays - 1) : null;
  const pick = (day: string) => {
    const next = pickDay(value, phase, day);
    setPhase(next.phase);
    setActive(day);
    onChange(next.range);
  };
  const onGridKey = (event: KeyboardEvent) => {
    const step = KEY_STEP[event.key];
    if (step === undefined) return;
    event.preventDefault();
    const next = shiftDay(active, step);
    moved.current = true;
    setActive(next);
    setView(monthOf(next));
  };
  const turn = (step: number) => setView((current) => monthOf(isoOf(current.year, current.month + step, 1)));
  const title = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(view.year, view.month, 1)));
  const weekdays = t("business.date_picker.weekdays", "lu ma mi ju vi sá do").split(" ");
  const ends = (
    [["from", t("business.export.start", "From"), value.from], ["to", t("business.export.end", "Through"), value.to]] as const
  ).map(([key, name, day]) => {
    const current = (key === "from") === (phase === "start");
    return (
      <div key={key} data-testid={`range-${key}`} className={`min-w-0 flex-1 rounded-[12px] border px-3 py-2 ${current ? "border-[#2f5a49]" : "border-[#DCE0DA] dark:border-white/10"}`}>
        <p className="text-[12px] text-[#56635e] dark:text-white/70">{name}</p>
        <p className="text-[15px] font-medium tabular-nums text-[#172b26] dark:text-white">{formatDay(day, locale)}</p>
      </div>
    );
  });

  return (
    <div data-testid="range-calendar" aria-label={label} role="group">
      <div className="flex gap-2">{ends}</div>
      <p className="sr-only" aria-live="polite">{phase === "end" ? t("business.export.pick_end", "Now pick the last day") : ""}</p>
      <div className="mt-2 flex items-center justify-between">
        <button type="button" className={iconButton} aria-label={t("business.date_picker.previous_month", "Previous month")} onClick={() => turn(-1)}><ChevronLeft className="h-5 w-5" aria-hidden="true" /></button>
        <h3 className="font-display text-[16px] font-medium text-[#172b26] dark:text-white">{title.charAt(0).toLocaleUpperCase(locale) + title.slice(1)}</h3>
        <button type="button" className={iconButton} aria-label={t("business.date_picker.next_month", "Next month")} onClick={() => turn(1)}><ChevronRight className="h-5 w-5" aria-hidden="true" /></button>
      </div>
      <table role="grid" aria-label={title} className="w-full border-collapse" onKeyDown={onGridKey}>
        <thead>
          <tr>{weekdays.map((day) => <th key={day} scope="col" className="h-8 text-[12px] font-medium text-[#56635e] dark:text-white/70">{day}</th>)}</tr>
        </thead>
        <tbody>
          {weeks(view).map((week, row) => (
            <tr key={row}>
              {week.map((day, column) => {
                if (!day) return <td key={`empty-${column}`} />;
                const edge = day === value.from || day === value.to;
                const inside = day > value.from && day < value.to;
                const blocked = latest !== null && day > latest;
                return (
                  <td key={day} role="gridcell" aria-selected={edge || inside} className={`p-0 text-center ${inside ? `bg-[#E3EBE1] dark:bg-[#8fcbb0]/15 ${column === 0 ? "rounded-l-full" : ""} ${column === 6 ? "rounded-r-full" : ""}` : ""} ${day === value.from && value.to > value.from ? "rounded-l-full bg-[#E3EBE1] dark:bg-[#8fcbb0]/15" : ""} ${day === value.to && value.to > value.from ? "rounded-r-full bg-[#E3EBE1] dark:bg-[#8fcbb0]/15" : ""}`}>
                    <button
                      type="button"
                      ref={day === active ? activeDay : undefined}
                      tabIndex={day === active ? 0 : -1}
                      disabled={blocked}
                      aria-label={formatDay(day, locale)}
                      data-day={day}
                      onClick={() => pick(day)}
                      className={`h-11 w-11 rounded-full text-[15px] tabular-nums disabled:opacity-30 ${focusRing} ${edge ? "bg-[#2f5a49] font-medium text-[#FFFEFA] dark:bg-[#8fcbb0] dark:text-[#172b26]" : "text-[#172b26] dark:text-white"}`}
                    >
                      {Number(day.slice(8))}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
